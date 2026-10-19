// Project BD baseband core: sample source mux, timebase, NCH tracking
// channels and the record collector behind one register bus.
// Register map and record format: docs/REGISTERS.md.
//
// The register bus runs in the sample clock domain here; the PCIe/AXI-Lite
// bridge and clock-domain crossing are added around this core in M2.
module bd_core #(
    parameter integer NCH     = 4,
    parameter integer CODE_AW = 14
) (
    input  wire         clk,
    input  wire         rst,

    // Live front end (NT1068: per path {sign, mag})
    input  wire         live_valid,
    input  wire [3:0]   live_sign,
    input  wire [3:0]   live_mag,

    // Host playback (four signed 4-bit samples per beat)
    input  wire         pb_valid,
    input  wire [15:0]  pb_data,

    // Register bus: write takes effect on the clock edge; read data is
    // valid on bus_rvalid, one cycle after bus_re.
    input  wire [15:0]  bus_addr,
    input  wire         bus_we,
    input  wire [31:0]  bus_wdata,
    input  wire         bus_re,
    output reg  [31:0]  bus_rdata,
    output reg          bus_rvalid,

    // Records to the host
    output wire         rec_valid,
    output wire [255:0] rec_data,
    input  wire         rec_ready,

    // Timing I/O
    output wire         pps_out,
    input  wire         event_in
);
    localparam [31:0] ID      = 32'h4244_3031;  // "BD01"
    localparam [31:0] VERSION = 32'h0001_0000;  // M1

    // ---------------- Global registers ----------------
    reg         src_playback;
    reg [15:0]  fe_map;
    reg [31:0]  tic_period, pps_period, pps_width;
    reg [31:0]  tic_next_lo, pps_next_lo;
    reg         tic_next_wr, pps_next_wr, overrun_clr;
    reg [63:0]  next_val;

    wire        glob = bus_addr[15:12] == 4'h0;
    wire        wr_g = bus_we && glob;

    always @(posedge clk) begin
        tic_next_wr <= 1'b0;
        pps_next_wr <= 1'b0;
        overrun_clr <= 1'b0;
        if (rst) begin
            src_playback <= 1'b0;
            fe_map       <= 16'hDF31;
            tic_period   <= 32'd0;
            pps_period   <= 32'd0;
            pps_width    <= 32'd0;
        end else if (wr_g) begin
            case (bus_addr[11:0])
                12'h00C: src_playback <= bus_wdata[0];
                12'h010: fe_map       <= bus_wdata[15:0];
                12'h014: tic_period   <= bus_wdata;
                12'h018: tic_next_lo  <= bus_wdata;
                12'h01C: begin next_val <= {bus_wdata, tic_next_lo}; tic_next_wr <= 1'b1; end
                12'h020: pps_period   <= bus_wdata;
                12'h024: pps_width    <= bus_wdata;
                12'h028: pps_next_lo  <= bus_wdata;
                12'h02C: begin next_val <= {bus_wdata, pps_next_lo}; pps_next_wr <= 1'b1; end
                12'h04C: overrun_clr  <= bus_wdata[0];
                default: ;
            endcase
        end
    end

    // ---------------- Sample path ----------------
    wire        m_valid;
    wire [15:0] m_data;
    sample_mux u_mux (
        .clk(clk), .rst(rst), .src_playback(src_playback), .fe_map(fe_map),
        .live_valid(live_valid), .live_sign(live_sign), .live_mag(live_mag),
        .pb_valid(pb_valid), .pb_data(pb_data),
        .out_valid(m_valid), .out_data(m_data)
    );

    wire        tic;
    wire [63:0] sample_cnt, last_tic_cnt, event_cnt;
    wire [31:0] event_count;
    timebase u_tb (
        .clk(clk), .rst(rst), .sample_valid(m_valid),
        .tic_period(tic_period), .tic_next_wr(tic_next_wr), .tic_next_in(next_val),
        .tic(tic), .last_tic_cnt(last_tic_cnt),
        .pps_period(pps_period), .pps_width(pps_width),
        .pps_next_wr(pps_next_wr), .pps_next_in(next_val), .pps_out(pps_out),
        .event_in(event_in), .event_cnt(event_cnt), .event_count(event_count),
        .sample_cnt(sample_cnt)
    );

    // One register stage on the fan-out to the channels
    reg        s_valid, s_tic;
    reg [15:0] s_data;
    always @(posedge clk) begin
        s_valid <= !rst && m_valid;
        s_tic   <= !rst && tic;
        s_data  <= m_data;
    end

    // ---------------- Channels ----------------
    // Channel c occupies 0x1000 + 0x40*c (c < 192, so bus_addr[15:14] == 0)
    wire        chan   = !glob && bus_addr[15:14] == 2'b00;
    wire [7:0]  ch_idx = bus_addr[13:6] - 8'h40;
    wire        overrun;
    channel_bank #(.NCH(NCH), .CODE_AW(CODE_AW)) u_bank (
        .clk(clk), .rst(rst),
        .s_valid(s_valid), .s_data(s_data), .s_tic(s_tic), .tic_cnt(last_tic_cnt),
        .wr_en(bus_we && chan), .ch_sel({4'd0, ch_idx}), .reg_idx(bus_addr[5:2]),
        .wr_data(bus_wdata),
        .rec_valid(rec_valid), .rec_data(rec_data), .rec_ready(rec_ready),
        .overrun(overrun), .overrun_clr(overrun_clr)
    );

    // ---------------- Reads ----------------
    reg [31:0] sample_hi, event_hi;
    always @(posedge clk) begin
        bus_rvalid <= bus_re;
        if (bus_re) begin
            case (glob ? bus_addr[11:0] : 12'hFFF)
                12'h000: bus_rdata <= ID;
                12'h004: bus_rdata <= VERSION;
                12'h008: bus_rdata <= NCH;
                12'h00C: bus_rdata <= {31'd0, src_playback};
                12'h010: bus_rdata <= {16'd0, fe_map};
                12'h014: bus_rdata <= tic_period;
                12'h020: bus_rdata <= pps_period;
                12'h024: bus_rdata <= pps_width;
                12'h030: begin bus_rdata <= sample_cnt[31:0]; sample_hi <= sample_cnt[63:32]; end
                12'h034: bus_rdata <= sample_hi;
                12'h038: begin bus_rdata <= event_cnt[31:0]; event_hi <= event_cnt[63:32]; end
                12'h03C: bus_rdata <= event_hi;
                12'h040: bus_rdata <= event_count;
                12'h044: bus_rdata <= last_tic_cnt[31:0];
                12'h048: bus_rdata <= last_tic_cnt[63:32];
                12'h04C: bus_rdata <= {31'd0, overrun};
                default: bus_rdata <= 32'hDEAD_BEEF;
            endcase
        end
    end
endmodule
