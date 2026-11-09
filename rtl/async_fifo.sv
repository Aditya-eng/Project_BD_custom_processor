// Dual-clock FIFO with gray-code pointers (first-word fall-through on the read side).
//
// Pointers are AW+1 bits; each side sees the other's gray pointer through a 2-FF
// synchronizer, so full/empty are conservative (never wrong, at most two cycles late).
// Memory is written in the write domain and read combinationally at the read pointer,
// which only addresses entries already visible as written. Each side has its own
// synchronous reset; reset both before use.
//
// Our own RTL, not a vendor macro, so it simulates in Icarus and carries over to an
// ASIC (docs/LICENSES.md rule 4).
module async_fifo #(
    parameter integer W  = 32,
    parameter integer AW = 4            // depth = 2^AW, AW >= 2
) (
    input  wire          wclk,
    input  wire          wrst,
    input  wire [W-1:0]  wdata,
    input  wire          wvalid,
    output wire          wready,        // not full

    input  wire          rclk,
    input  wire          rrst,
    output wire [W-1:0]  rdata,
    output wire          rvalid,        // not empty
    input  wire          rready
);
    reg [W-1:0] mem [0:(1<<AW)-1];

    function automatic [AW:0] bin2gray(input [AW:0] b);
        bin2gray = b ^ (b >> 1);
    endfunction

    // ---------------- write side ----------------
    reg  [AW:0] wbin, wgray;
    (* ASYNC_REG = "TRUE" *) reg [AW:0] rgray_w1, rgray_w2;
    assign wready = !(wgray == {~rgray_w2[AW:AW-1], rgray_w2[AW-2:0]});
    wire  [AW:0] wbin_n = wbin + 1'b1;

    always @(posedge wclk) begin
        if (wrst) begin
            wbin <= 0;
            wgray <= 0;
            rgray_w1 <= 0;
            rgray_w2 <= 0;
        end else begin
            rgray_w1 <= rgray;
            rgray_w2 <= rgray_w1;
            if (wvalid && wready) begin
                mem[wbin[AW-1:0]] <= wdata;
                wbin  <= wbin_n;
                wgray <= bin2gray(wbin_n);
            end
        end
    end

    // ---------------- read side ----------------
    reg  [AW:0] rbin, rgray;
    (* ASYNC_REG = "TRUE" *) reg [AW:0] wgray_r1, wgray_r2;
    assign rvalid = !(rgray == wgray_r2);
    assign rdata  = mem[rbin[AW-1:0]];
    wire  [AW:0] rbin_n = rbin + 1'b1;

    always @(posedge rclk) begin
        if (rrst) begin
            rbin <= 0;
            rgray <= 0;
            wgray_r1 <= 0;
            wgray_r2 <= 0;
        end else begin
            wgray_r1 <= wgray;
            wgray_r2 <= wgray_r1;
            if (rvalid && rready) begin
                rbin  <= rbin_n;
                rgray <= bin2gray(rbin_n);
            end
        end
    end
endmodule
