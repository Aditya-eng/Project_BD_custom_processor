// NCH tracking channels, their register files, and the record collector.
//
// Register writes arrive on a simple bus (word offset `reg_idx` within the
// channel selected by `ch_sel`); see docs/REGISTERS.md. Control words are
// shadowed: CARR_FCW/CODE_FCW take effect together on CMD.commit or CMD.load.
//
// Collector: every dump and measurement latch sets a pending flag. A scan
// pointer visits one channel per cycle and emits one 256-bit record per
// pending item (dump first). A channel that produces a new item before its
// previous one was emitted sets the sticky `overrun` flag. With one record
// per cycle the worst-case drain after a tic is 2*NCH cycles, so the tic
// period must exceed that (it is >= 1 ms in practice).
module channel_bank #(
    parameter integer NCH     = 4,
    parameter integer CODE_AW = 14,
    parameter integer CH_W    = 12
) (
    input  wire                clk,
    input  wire                rst,

    // Sample bus
    input  wire                s_valid,
    input  wire [15:0]         s_data,
    input  wire                s_tic,
    input  wire [63:0]         tic_cnt,      // sample index of the last tic

    // Register write bus
    input  wire                wr_en,
    input  wire [CH_W-1:0]     ch_sel,
    input  wire [3:0]          reg_idx,
    input  wire [31:0]         wr_data,

    // Record stream
    output reg                 rec_valid,
    output reg  [255:0]        rec_data,
    input  wire                rec_ready,
    output reg                 overrun,
    input  wire                overrun_clr
);
    localparam [3:0] R_CARR = 4'd0, R_CODE = 4'd1, R_SPACING = 4'd2, R_CODE_LEN = 4'd3,
                     R_PATH = 4'd4, R_LD_CARR = 4'd5, R_LD_FRAC = 4'd6, R_LD_CHIP = 4'd7,
                     R_CMD = 4'd8, R_WADDR = 4'd9, R_WDATA = 4'd10;
    localparam [3:0] T_DUMP = 4'd1, T_MEAS = 4'd2;

    // Per-channel outputs gathered for the collector
    wire                 dump_v   [0:NCH-1];
    wire                 meas_v   [0:NCH-1];
    wire [15:0]          d_epoch  [0:NCH-1];
    wire [32*6-1:0]      d_vals   [0:NCH-1];
    wire [31:0]          m_cp     [0:NCH-1];
    wire [31:0]          m_cyc    [0:NCH-1];
    wire [31:0]          m_frac   [0:NCH-1];
    wire [CODE_AW-1:0]   m_chip   [0:NCH-1];
    wire [15:0]          m_epoch  [0:NCH-1];

    genvar c;
    generate
        for (c = 0; c < NCH; c = c + 1) begin : g_ch
            wire sel = wr_en && (ch_sel == c);

            reg [31:0]        carr_sh, code_sh, carr_act, code_act, spacing;
            reg [CODE_AW:0]   code_len;
            reg [1:0]         path;
            reg [31:0]        ld_carr, ld_frac;
            reg [CODE_AW-1:0] ld_chip, waddr;
            reg               load, code_we, code_wbit;
            reg [CODE_AW-1:0] code_waddr;

            always @(posedge clk) begin
                load    <= 1'b0;
                code_we <= 1'b0;
                if (rst) begin
                    {carr_sh, code_sh, carr_act, code_act} <= 128'd0;
                    spacing  <= 32'h8000_0000;
                    code_len <= 1023;
                    path     <= 2'd0;
                    waddr    <= {CODE_AW{1'b0}};
                end else if (sel) begin
                    case (reg_idx)
                        R_CARR:     carr_sh  <= wr_data;
                        R_CODE:     code_sh  <= wr_data;
                        R_SPACING:  spacing  <= wr_data;
                        R_CODE_LEN: code_len <= wr_data[CODE_AW:0];
                        R_PATH:     path     <= wr_data[1:0];
                        R_LD_CARR:  ld_carr  <= wr_data;
                        R_LD_FRAC:  ld_frac  <= wr_data;
                        R_LD_CHIP:  ld_chip  <= wr_data[CODE_AW-1:0];
                        R_CMD: begin
                            if (wr_data[0] || wr_data[1]) begin
                                carr_act <= carr_sh;
                                code_act <= code_sh;
                            end
                            load <= wr_data[1];
                        end
                        R_WADDR:    waddr    <= wr_data[CODE_AW-1:0];
                        R_WDATA: begin
                            code_we    <= 1'b1;
                            code_waddr <= waddr;
                            code_wbit  <= wr_data[0];
                            waddr      <= waddr + 1'b1;
                        end
                        default: ;
                    endcase
                end
            end

            wire signed [3:0] smp = s_data[4*path +: 4];
            wire signed [31:0] ie, qe, ip, qp, il, ql;

            track_channel #(.IN_W(4), .CODE_AW(CODE_AW)) u_ch (
                .clk(clk), .rst(rst),
                .sample(smp), .sample_valid(s_valid), .tic(s_tic),
                .carr_fcw(carr_act), .code_fcw(code_act), .half_spacing(spacing),
                .code_len(code_len),
                .load(load), .load_carr_phase(ld_carr), .load_code_frac(ld_frac),
                .load_chip_idx(ld_chip),
                .code_we(code_we), .code_waddr(code_waddr), .code_wdata(code_wbit),
                .dump_valid(dump_v[c]), .dump_epoch(d_epoch[c]),
                .ie(ie), .qe(qe), .ip(ip), .qp(qp), .il(il), .ql(ql),
                .meas_valid(meas_v[c]), .meas_carr_phase(m_cp[c]), .meas_carr_cycles(m_cyc[c]),
                .meas_code_frac(m_frac[c]), .meas_chip_idx(m_chip[c]), .meas_epoch(m_epoch[c])
            );
            assign d_vals[c] = {ql, il, qp, ip, qe, ie};
        end
    endgenerate

    // ---------------- Collector ----------------
    reg [NCH-1:0]  pend_d, pend_m;
    localparam integer PW = (NCH > 1) ? $clog2(NCH) : 1;
    reg [CH_W-1:0] ptr;
    wire [PW-1:0]  pi       = ptr[PW-1:0];
    wire           can_emit = !rec_valid || rec_ready;
    wire           take_d   = can_emit && pend_d[pi];
    wire           take_m   = can_emit && !pend_d[pi] && pend_m[pi];

    integer k;
    always @(posedge clk) begin
        if (rst) begin
            pend_d    <= {NCH{1'b0}};
            pend_m    <= {NCH{1'b0}};
            ptr       <= {CH_W{1'b0}};
            rec_valid <= 1'b0;
            overrun   <= 1'b0;
        end else begin
            if (rec_valid && rec_ready)
                rec_valid <= 1'b0;
            if (overrun_clr)
                overrun <= 1'b0;

            if (take_d) begin
                rec_valid <= 1'b1;
                rec_data  <= {32'd0, d_vals[pi], T_DUMP, ptr, d_epoch[pi]};
            end else if (take_m) begin
                rec_valid <= 1'b1;
                rec_data  <= {32'd0, tic_cnt,
                              {{(32-CODE_AW){1'b0}}, m_chip[pi]}, m_frac[pi], m_cyc[pi], m_cp[pi],
                              T_MEAS, ptr, m_epoch[pi]};
            end else if (can_emit) begin
                ptr <= (ptr == CH_W'(NCH - 1)) ? {CH_W{1'b0}} : ptr + 1'b1;
            end

            for (k = 0; k < NCH; k = k + 1) begin
                if (dump_v[k]) begin
                    if (pend_d[k]) overrun <= 1'b1;
                    pend_d[k] <= !(take_d && ptr == CH_W'(k));
                end else if (take_d && ptr == CH_W'(k)) begin
                    pend_d[k] <= 1'b0;
                end
                if (meas_v[k]) begin
                    if (pend_m[k]) overrun <= 1'b1;
                    pend_m[k] <= !(take_m && ptr == CH_W'(k));
                end else if (take_m && ptr == CH_W'(k)) begin
                    pend_m[k] <= 1'b0;
                end
            end
        end
    end
endmodule
