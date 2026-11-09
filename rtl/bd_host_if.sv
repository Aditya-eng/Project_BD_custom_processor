// bd_core behind the PCIe/XDMA interfaces (M2): AXI4-Lite registers and two AXI4-Stream
// DMA channels in the PCIe clock domain (aclk); bd_core runs on the sample clock (fe_clk).
//
// - Registers: axil_bus_bridge (toggle handshake, one transaction at a time; addresses
//   unchanged from docs/REGISTERS.md).
// - H2C playback: W-bit beats, each holding W/16 samples (sample i in bits [16i+15:16i],
//   four signed 4-bit paths per sample), through an async FIFO; unpacked in the sample
//   domain to at most one sample per fe_clk. Backpressure reaches the host, so playback
//   never drops samples. Partial beats (tkeep) are not supported: send whole beats.
// - C2H records: 256-bit collector records through an async FIFO, sent as 256/W beats each.
//   tlast closes a packet after PKT_RECS records. A record that waits alone would hold a
//   DMA read open, so after FLUSH_CYCLES idle aclk cycles with a partial packet the
//   interface appends one pad record (all zero, type 0) with tlast. Hosts skip type 0.
// - Reset: aresetn (aclk domain, active low) also resets the sample domain through a
//   synchronizer.
module bd_host_if #(
    parameter integer NCH          = 4,
    parameter integer CODE_AW      = 14,
    parameter integer W            = 128,     // AXI-Stream width: 64, 128 or 256
    parameter integer H2C_AW       = 9,       // playback FIFO depth 2^H2C_AW beats
    parameter integer C2H_AW       = 5,       // record FIFO depth 2^C2H_AW records
    parameter integer PKT_RECS     = 64,
    parameter integer FLUSH_CYCLES = 25000,   // 100 us at 250 MHz
    parameter integer BUS_TIMEOUT  = 65536
) (
    // PCIe / XDMA domain
    input  wire           aclk,
    input  wire           aresetn,

    input  wire [15:0]    s_axil_awaddr,
    input  wire           s_axil_awvalid,
    output wire           s_axil_awready,
    input  wire [31:0]    s_axil_wdata,
    input  wire           s_axil_wvalid,
    output wire           s_axil_wready,
    output wire [1:0]     s_axil_bresp,
    output wire           s_axil_bvalid,
    input  wire           s_axil_bready,
    input  wire [15:0]    s_axil_araddr,
    input  wire           s_axil_arvalid,
    output wire           s_axil_arready,
    output wire [31:0]    s_axil_rdata,
    output wire [1:0]     s_axil_rresp,
    output wire           s_axil_rvalid,
    input  wire           s_axil_rready,

    input  wire [W-1:0]   s_axis_h2c_tdata,
    input  wire           s_axis_h2c_tvalid,
    output wire           s_axis_h2c_tready,

    output wire [W-1:0]   m_axis_c2h_tdata,
    output wire [W/8-1:0] m_axis_c2h_tkeep,
    output wire           m_axis_c2h_tlast,
    output wire           m_axis_c2h_tvalid,
    input  wire           m_axis_c2h_tready,

    // Sample clock domain
    input  wire           fe_clk,
    input  wire           live_valid,
    input  wire [3:0]     live_sign,
    input  wire [3:0]     live_mag,
    output wire           pps_out,
    input  wire           event_in
);
    localparam integer SPB = W / 16;          // samples per H2C beat
    localparam integer BPR = 256 / W;         // beats per record
    localparam integer SW  = (SPB > 1) ? $clog2(SPB) : 1;
    localparam integer BW  = (BPR > 1) ? $clog2(BPR) : 1;

    // ---------------- resets ----------------
    reg arst;
    always @(posedge aclk) arst <= !aresetn;
    (* ASYNC_REG = "TRUE" *) reg fe_rst1, fe_rst2;
    reg fe_rst;
    always @(posedge fe_clk) begin
        fe_rst1 <= !aresetn;
        fe_rst2 <= fe_rst1;
        fe_rst  <= fe_rst2;
    end

    // ---------------- registers ----------------
    wire [15:0] bus_addr;
    wire        bus_we, bus_re, bus_rvalid;
    wire [31:0] bus_wdata, bus_rdata;
    axil_bus_bridge #(.TIMEOUT(BUS_TIMEOUT)) u_bridge (
        .aclk(aclk), .arst(arst),
        .s_awaddr(s_axil_awaddr), .s_awvalid(s_axil_awvalid), .s_awready(s_axil_awready),
        .s_wdata(s_axil_wdata), .s_wvalid(s_axil_wvalid), .s_wready(s_axil_wready),
        .s_bresp(s_axil_bresp), .s_bvalid(s_axil_bvalid), .s_bready(s_axil_bready),
        .s_araddr(s_axil_araddr), .s_arvalid(s_axil_arvalid), .s_arready(s_axil_arready),
        .s_rdata(s_axil_rdata), .s_rresp(s_axil_rresp), .s_rvalid(s_axil_rvalid),
        .s_rready(s_axil_rready),
        .bclk(fe_clk), .brst(fe_rst),
        .bus_addr(bus_addr), .bus_we(bus_we), .bus_wdata(bus_wdata), .bus_re(bus_re),
        .bus_rdata(bus_rdata), .bus_rvalid(bus_rvalid)
    );

    // ---------------- H2C playback ----------------
    wire [W-1:0] pb_beat;
    wire         pb_beat_valid;
    reg  [SW-1:0] pb_idx;
    wire         pb_last = (pb_idx == SW'(SPB - 1));
    async_fifo #(.W(W), .AW(H2C_AW)) u_h2c (
        .wclk(aclk), .wrst(arst), .wdata(s_axis_h2c_tdata), .wvalid(s_axis_h2c_tvalid),
        .wready(s_axis_h2c_tready),
        .rclk(fe_clk), .rrst(fe_rst), .rdata(pb_beat), .rvalid(pb_beat_valid),
        .rready(pb_beat_valid && pb_last)
    );
    always @(posedge fe_clk) begin
        if (fe_rst)
            pb_idx <= 0;
        else if (pb_beat_valid)
            pb_idx <= pb_last ? {SW{1'b0}} : pb_idx + 1'b1;
    end
    wire [15:0] pb_data = pb_beat[16 * pb_idx +: 16];

    // ---------------- core ----------------
    wire         rec_valid, rec_ready;
    wire [255:0] rec_data;
    bd_core #(.NCH(NCH), .CODE_AW(CODE_AW)) u_core (
        .clk(fe_clk), .rst(fe_rst),
        .live_valid(live_valid), .live_sign(live_sign), .live_mag(live_mag),
        .pb_valid(pb_beat_valid), .pb_data(pb_data),
        .bus_addr(bus_addr), .bus_we(bus_we), .bus_wdata(bus_wdata), .bus_re(bus_re),
        .bus_rdata(bus_rdata), .bus_rvalid(bus_rvalid),
        .rec_valid(rec_valid), .rec_data(rec_data), .rec_ready(rec_ready),
        .pps_out(pps_out), .event_in(event_in)
    );

    // ---------------- C2H records ----------------
    wire [255:0] r_data;
    wire         r_valid;
    reg  [BW-1:0] beat;
    reg  [7:0]   in_pkt;              // records sent in the current packet
    reg          pad;                 // sending a pad record
    reg  [$clog2(FLUSH_CYCLES + 1)-1:0] idle;
    wire         last_beat = (beat == BW'(BPR - 1));
    wire         sending   = r_valid || pad;
    wire         take      = sending && m_axis_c2h_tready;

    async_fifo #(.W(256), .AW(C2H_AW)) u_c2h (
        .wclk(fe_clk), .wrst(fe_rst), .wdata(rec_data), .wvalid(rec_valid),
        .wready(rec_ready),
        .rclk(aclk), .rrst(arst), .rdata(r_data), .rvalid(r_valid),
        .rready(take && last_beat && !pad)
    );

    assign m_axis_c2h_tvalid = sending;
    assign m_axis_c2h_tdata  = pad ? {W{1'b0}} : r_data[W * beat +: W];
    assign m_axis_c2h_tkeep  = {(W/8){1'b1}};
    assign m_axis_c2h_tlast  = last_beat && (pad || in_pkt == 8'(PKT_RECS - 1));

    always @(posedge aclk) begin
        if (arst) begin
            beat   <= 0;
            in_pkt <= 0;
            pad    <= 1'b0;
            idle   <= 0;
        end else begin
            if (take) begin
                idle <= 0;
                beat <= last_beat ? {BW{1'b0}} : beat + 1'b1;
                if (last_beat) begin
                    in_pkt <= m_axis_c2h_tlast ? 8'd0 : in_pkt + 1'b1;
                    pad    <= 1'b0;
                end
            end else if (!sending && in_pkt != 0) begin
                // A partial packet is waiting for more records: flush it after a while.
                if (idle == ($clog2(FLUSH_CYCLES + 1))'(FLUSH_CYCLES))
                    pad <= 1'b1;
                else
                    idle <= idle + 1'b1;
            end
        end
    end
endmodule
