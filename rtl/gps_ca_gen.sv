// GPS L1 C/A Gold code generator (IS-GPS-200 G1/G2 with G2 phase selector).
// Emits one chip per `step`. Used to fill a channel's code memory in hardware
// without a host download; bit-exact with model/bdmodel/gps_ca.py.
module gps_ca_gen (
    input  wire       clk,
    input  wire       rst,
    input  wire       init,      // reload both registers with all ones
    input  wire [3:0] tap1,      // G2 selector taps, 1-based stage numbers
    input  wire [3:0] tap2,
    input  wire       step,
    output wire       chip
);
    reg [10:1] g1, g2;

    assign chip = g1[10] ^ g2[tap1] ^ g2[tap2];

    always @(posedge clk) begin
        if (rst || init) begin
            g1 <= 10'h3FF;
            g2 <= 10'h3FF;
        end else if (step) begin
            g1 <= {g1[9:1], g1[3] ^ g1[10]};
            g2 <= {g2[9:1], g2[2] ^ g2[3] ^ g2[6] ^ g2[8] ^ g2[9] ^ g2[10]};
        end
    end
endmodule
