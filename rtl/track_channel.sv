// One tracking channel: carrier NCO + code NCO + E/P/L complex correlators
// + measurement latch. Processes one sample per clock when sample_valid.
//
// Bit-exact contract: model/bdmodel/correlator.py (see its module docstring
// and docs/ARCHITECTURE.md). Control words may change between any two
// samples; they take effect on the next accepted sample.
module track_channel #(
    parameter integer IN_W     = 4,      // signed sample width
    parameter integer CODE_AW  = 14,     // code memory address width (16384 chips)
    parameter integer ACC_W    = 32
) (
    input  wire                     clk,
    input  wire                     rst,

    // Sample stream (shared by all channels on the same RF path)
    input  wire signed [IN_W-1:0]   sample,
    input  wire                     sample_valid,
    input  wire                     tic,            // measurement latch, qualified by sample_valid

    // Control words
    input  wire signed [31:0]       carr_fcw,
    input  wire        [31:0]       code_fcw,       // must be < 2^31
    input  wire        [31:0]       half_spacing,   // D, chips * 2^32
    input  wire        [CODE_AW:0]  code_len,
    input  wire                     boc,            // BOC(1,1): XOR taps with their subcarrier phase
    input  wire                     tdm,            // time-multiplexed code: tap counts in one half-chip only
    input  wire                     tdm_slot,       // the half that counts (0: first, 1: second)

    // Load: sets NCO state, clears accumulators, epoch counter and pipeline
    input  wire                     load,
    input  wire        [31:0]       load_carr_phase,
    input  wire        [31:0]       load_code_frac,
    input  wire        [CODE_AW-1:0] load_chip_idx,

    // Code memory write port (1 bit per chip, logic 0 -> +1)
    input  wire                     code_we,
    input  wire        [CODE_AW-1:0] code_waddr,
    input  wire                     code_wdata,

    // Correlator dump, one per code epoch
    output reg                      dump_valid,
    output reg         [15:0]       dump_epoch,
    output reg  signed [ACC_W-1:0]  ie, qe, ip, qp, il, ql,

    // Measurement latch (state seen by the sample that carried `tic`)
    output reg                      meas_valid,
    output reg         [31:0]       meas_carr_phase,
    output reg  signed [31:0]       meas_carr_cycles,
    output reg         [31:0]       meas_code_frac,
    output reg         [CODE_AW-1:0] meas_chip_idx,
    output reg         [15:0]       meas_epoch
);
    `include "carrier_lut.svh"

    localparam integer PROD_W = IN_W + 5;

    // ---------------- NCO / code state ----------------
    reg        [31:0]        carr_phase;
    reg signed [31:0]        carr_cycles;
    reg        [31:0]        code_frac;
    reg        [CODE_AW-1:0] chip_idx;
    reg        [15:0]        epoch_cnt;

    reg code_mem [0:(1<<CODE_AW)-1];
    always @(posedge clk)
        if (code_we) code_mem[code_waddr] <= code_wdata;

    // ---------------- Stage A: taps from current state ----------------
    wire [4:0]  lut_idx = carr_phase[31:27];
    wire signed [4:0] lcos = carr_cos(lut_idx);
    wire signed [4:0] lsin = carr_sin(lut_idx);

    wire        e_adv   = code_frac > ~half_spacing;   // carry of code_frac + D
    wire        l_dec   = code_frac < half_spacing;
    // Sine-phased BOC(1,1) subcarrier and the TDM half-chip are both the MSB of
    // each tap's own fractional phase.
    /* verilator lint_off UNUSEDSIGNAL */   // only bit 31 is used
    wire [31:0] e_frac  = code_frac + half_spacing;
    wire [31:0] l_frac  = code_frac - half_spacing;
    /* verilator lint_on UNUSEDSIGNAL */
    wire [CODE_AW:0] chip_p1 = {1'b0, chip_idx} + 1'b1;
    wire [CODE_AW-1:0] e_idx = !e_adv ? chip_idx
                               : (chip_p1 == code_len ? {CODE_AW{1'b0}} : chip_p1[CODE_AW-1:0]);
    wire [CODE_AW-1:0] l_idx = !l_dec ? chip_idx
                               : (chip_idx == 0 ? code_len[CODE_AW-1:0] - 1'b1 : chip_idx - 1'b1);

    // Carrier advance with signed wrap direction
    wire [33:0] carr_sum = {2'b00, carr_phase} + {{2{carr_fcw[31]}}, carr_fcw};
    wire signed [31:0] carr_dcyc = {{30{carr_sum[33]}}, carr_sum[33:32]};

    // Code advance
    wire [32:0] code_sum  = {1'b0, code_frac} + {1'b0, code_fcw};
    wire        chip_adv  = code_sum[32];
    wire        last_chip = (chip_p1 == code_len);
    wire        wrap      = chip_adv && last_chip;

    // ---------------- Stage B registers ----------------
    reg                     b_valid, b_dump;
    reg signed [PROD_W-1:0] b_i, b_q;
    reg                     b_e, b_p, b_l;
    reg                     b_ze, b_zp, b_zl;   // tap gated off (TDM mode)

    always @(posedge clk) begin
        meas_valid <= 1'b0;
        if (rst || load) begin
            carr_phase  <= rst ? 32'd0 : load_carr_phase;
            carr_cycles <= 32'sd0;
            code_frac   <= rst ? 32'd0 : load_code_frac;
            chip_idx    <= rst ? {CODE_AW{1'b0}} : load_chip_idx;
            epoch_cnt   <= 16'd0;
            b_valid     <= 1'b0;
            b_dump      <= 1'b0;
        end else begin
            b_valid <= sample_valid;
            b_dump  <= sample_valid && wrap;
            if (sample_valid) begin
                b_i <= sample * lcos;
                b_q <= -(sample * lsin);
                b_e <= code_mem[e_idx]    ^ (boc & e_frac[31]);
                b_p <= code_mem[chip_idx] ^ (boc & code_frac[31]);
                b_l <= code_mem[l_idx]    ^ (boc & l_frac[31]);
                b_ze <= tdm & (e_frac[31]    ^ tdm_slot);
                b_zp <= tdm & (code_frac[31] ^ tdm_slot);
                b_zl <= tdm & (l_frac[31]    ^ tdm_slot);

                if (tic) begin
                    meas_valid       <= 1'b1;
                    meas_carr_phase  <= carr_phase;
                    meas_carr_cycles <= carr_cycles;
                    meas_code_frac   <= code_frac;
                    meas_chip_idx    <= chip_idx;
                    meas_epoch       <= epoch_cnt;
                end

                carr_phase  <= carr_sum[31:0];
                carr_cycles <= carr_cycles + carr_dcyc;
                code_frac   <= code_sum[31:0];
                if (chip_adv)
                    chip_idx <= last_chip ? {CODE_AW{1'b0}} : chip_p1[CODE_AW-1:0];
                if (wrap)
                    epoch_cnt <= epoch_cnt + 1'b1;
            end
        end
    end

    // ---------------- Stage C: accumulate / dump ----------------
    reg signed [ACC_W-1:0] acc_ie, acc_qe, acc_ip, acc_qp, acc_il, acc_ql;

    wire signed [ACC_W-1:0] xi = {{(ACC_W-PROD_W){b_i[PROD_W-1]}}, b_i};
    wire signed [ACC_W-1:0] xq = {{(ACC_W-PROD_W){b_q[PROD_W-1]}}, b_q};
    wire signed [ACC_W-1:0] ie_n = acc_ie + (b_ze ? 0 : b_e ? -xi : xi);
    wire signed [ACC_W-1:0] qe_n = acc_qe + (b_ze ? 0 : b_e ? -xq : xq);
    wire signed [ACC_W-1:0] ip_n = acc_ip + (b_zp ? 0 : b_p ? -xi : xi);
    wire signed [ACC_W-1:0] qp_n = acc_qp + (b_zp ? 0 : b_p ? -xq : xq);
    wire signed [ACC_W-1:0] il_n = acc_il + (b_zl ? 0 : b_l ? -xi : xi);
    wire signed [ACC_W-1:0] ql_n = acc_ql + (b_zl ? 0 : b_l ? -xq : xq);

    // A sample already in stage B when `load` arrives still completes (so an
    // epoch that ended just before the load is still dumped); `load` then
    // clears the accumulators. A sample presented in the same cycle as `load`
    // is dropped.
    always @(posedge clk) begin
        dump_valid <= 1'b0;
        if (rst) begin
            {acc_ie, acc_qe, acc_ip, acc_qp, acc_il, acc_ql} <= {6*ACC_W{1'b0}};
        end else begin
            if (b_valid) begin
                if (b_dump) begin
                    {ie, qe, ip, qp, il, ql} <= {ie_n, qe_n, ip_n, qp_n, il_n, ql_n};
                    dump_valid <= 1'b1;
                    dump_epoch <= epoch_cnt;   // already incremented by stage A
                    {acc_ie, acc_qe, acc_ip, acc_qp, acc_il, acc_ql} <= {6*ACC_W{1'b0}};
                end else begin
                    {acc_ie, acc_qe, acc_ip, acc_qp, acc_il, acc_ql} <= {ie_n, qe_n, ip_n, qp_n, il_n, ql_n};
                end
            end
            if (load)
                {acc_ie, acc_qe, acc_ip, acc_qp, acc_il, acc_ql} <= {6*ACC_W{1'b0}};
        end
    end
endmodule
