// AXI4-Lite slave (PCIe clock) to the bd_core register bus (sample clock).
//
// One transaction at a time. The AXI side captures address/data, then toggles `req`;
// the bus side sees the toggle through a 2-FF synchronizer, performs one bus write or
// read, and toggles `ack` back. The captured registers are stable for the whole
// handshake, so only the toggles cross unsynchronized. Order is preserved, so the
// latching reads (SAMPLE_CNT_LO then _HI) and CMD commits keep their meaning.
//
// If the sample clock is absent (e.g. no front end in M3), an access would never
// complete and would stall the PCIe link. After TIMEOUT PCIe clocks without an ack the
// bridge answers SLVERR (reads return 0xDEADBEEF). A transaction already handed over is
// still performed when the sample clock returns; new ones answer SLVERR immediately
// until it has been.
module axil_bus_bridge #(
    parameter integer TIMEOUT = 65536
) (
    input  wire         aclk,
    input  wire         arst,

    input  wire [15:0]  s_awaddr,
    input  wire         s_awvalid,
    output reg          s_awready,
    input  wire [31:0]  s_wdata,
    input  wire         s_wvalid,
    output reg          s_wready,
    output reg  [1:0]   s_bresp,
    output reg          s_bvalid,
    input  wire         s_bready,
    input  wire [15:0]  s_araddr,
    input  wire         s_arvalid,
    output reg          s_arready,
    output reg  [31:0]  s_rdata,
    output reg  [1:0]   s_rresp,
    output reg          s_rvalid,
    input  wire         s_rready,

    input  wire         bclk,
    input  wire         brst,
    output reg  [15:0]  bus_addr,
    output reg          bus_we,
    output reg  [31:0]  bus_wdata,
    output reg          bus_re,
    input  wire [31:0]  bus_rdata,
    input  wire         bus_rvalid
);
    localparam [1:0] OKAY = 2'b00, SLVERR = 2'b10;
    localparam integer TW = $clog2(TIMEOUT + 1);

    reg        ack;                  // bus side -> AXI side toggle
    reg [31:0] rdata_b;              // bus-side read data, stable once ack has toggled

    // ---------------- AXI side ----------------
    localparam [2:0] A_IDLE = 3'd0, A_ISSUE = 3'd1, A_WAIT = 3'd2, A_REFUSE = 3'd3,
                     A_RESP = 3'd4;
    reg  [2:0]  a_state;
    reg         req, cap_we;
    reg  [15:0] cap_addr;
    reg  [31:0] cap_wdata;
    reg  [TW-1:0] wait_cnt;
    (* ASYNC_REG = "TRUE" *) reg ack_a1, ack_a2;
    wire        idle_hs = (req == ack_a2);          // no transaction in flight

    task automatic respond(input ok);
        if (cap_we) begin
            s_bresp  <= ok ? OKAY : SLVERR;
            s_bvalid <= 1'b1;
        end else begin
            s_rdata  <= ok ? rdata_b : 32'hDEAD_BEEF;
            s_rresp  <= ok ? OKAY : SLVERR;
            s_rvalid <= 1'b1;
        end
    endtask

    always @(posedge aclk) begin
        s_awready <= 1'b0;
        s_wready  <= 1'b0;
        s_arready <= 1'b0;
        if (arst) begin
            a_state  <= A_IDLE;
            req      <= 1'b0;
            ack_a1   <= 1'b0;
            ack_a2   <= 1'b0;
            s_bvalid <= 1'b0;
            s_rvalid <= 1'b0;
            wait_cnt <= 0;
        end else begin
            ack_a1 <= ack;
            ack_a2 <= ack_a1;
            case (a_state)
                A_IDLE: begin
                    wait_cnt <= 0;
                    if (s_awvalid && s_wvalid) begin
                        s_awready <= 1'b1;
                        s_wready  <= 1'b1;
                        cap_we    <= 1'b1;
                        if (idle_hs) begin
                            cap_addr  <= s_awaddr;
                            cap_wdata <= s_wdata;
                            a_state   <= A_ISSUE;
                        end else begin
                            a_state   <= A_REFUSE;   // an earlier timed-out access is pending
                        end
                    end else if (s_arvalid) begin
                        s_arready <= 1'b1;
                        cap_we    <= 1'b0;
                        if (idle_hs) begin
                            cap_addr <= s_araddr;
                            a_state  <= A_ISSUE;
                        end else begin
                            a_state  <= A_REFUSE;
                        end
                    end
                end
                A_ISSUE: begin                       // captured registers settle first
                    req     <= ~req;
                    a_state <= A_WAIT;
                end
                A_REFUSE: begin                      // respond after the handshake (AXI rule)
                    respond(1'b0);
                    a_state <= A_RESP;
                end
                A_WAIT: begin
                    if (idle_hs) begin
                        respond(1'b1);
                        a_state <= A_RESP;
                    end else if (wait_cnt == TW'(TIMEOUT)) begin
                        respond(1'b0);
                        a_state <= A_RESP;
                    end else begin
                        wait_cnt <= wait_cnt + 1'b1;
                    end
                end
                default: begin   // A_RESP
                    if (s_bvalid && s_bready) s_bvalid <= 1'b0;
                    if (s_rvalid && s_rready) s_rvalid <= 1'b0;
                    if ((s_bvalid && s_bready) || (s_rvalid && s_rready)) a_state <= A_IDLE;
                end
            endcase
        end
    end

    // ---------------- bus side ----------------
    (* ASYNC_REG = "TRUE" *) reg req_b1, req_b2;
    reg        req_b3, busy;

    always @(posedge bclk) begin
        bus_we <= 1'b0;
        bus_re <= 1'b0;
        if (brst) begin
            req_b1 <= 1'b0;
            req_b2 <= 1'b0;
            req_b3 <= 1'b0;
            ack    <= 1'b0;
            busy   <= 1'b0;
        end else begin
            req_b1 <= req;
            req_b2 <= req_b1;
            req_b3 <= req_b2;
            if (req_b2 != req_b3) begin                 // new transaction
                bus_addr  <= cap_addr;
                bus_wdata <= cap_wdata;
                if (cap_we) begin
                    bus_we <= 1'b1;
                    ack    <= ~ack;
                end else begin
                    bus_re <= 1'b1;
                    busy   <= 1'b1;
                end
            end
            if (busy && bus_rvalid) begin
                rdata_b <= bus_rdata;
                busy    <= 1'b0;
                ack     <= ~ack;
            end
        end
    end
endmodule
