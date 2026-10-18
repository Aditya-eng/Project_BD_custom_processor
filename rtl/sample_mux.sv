// Selects the live front end or host playback and maps samples onto the
// 4-path signed sample bus (path p in bits [4p+3:4p]).
//
// Live input: per path a 2-bit ADC code {sign, mag}. fe_map holds the signed
// 4-bit value for each code (entry c in bits [4c+3:4c]), so the polarity and
// level convention of the front end is set by the host. Default 0xDF31:
// {0,0}->+1, {0,1}->+3, {1,0}->-1, {1,1}->-3.
// Playback input: four signed 4-bit samples per beat, already mapped.
module sample_mux (
    input  wire        clk,
    input  wire        rst,
    input  wire        src_playback,
    input  wire [15:0] fe_map,

    input  wire        live_valid,
    input  wire [3:0]  live_sign,
    input  wire [3:0]  live_mag,

    input  wire        pb_valid,
    input  wire [15:0] pb_data,

    output reg         out_valid,
    output reg  [15:0] out_data
);
    function automatic [3:0] map_code(input [15:0] m, input s, input g);
        case ({s, g})
            2'b00: map_code = m[3:0];
            2'b01: map_code = m[7:4];
            2'b10: map_code = m[11:8];
            default: map_code = m[15:12];
        endcase
    endfunction

    wire [15:0] live_data;
    genvar p;
    generate
        for (p = 0; p < 4; p = p + 1) begin : g_map
            assign live_data[4*p +: 4] = map_code(fe_map, live_sign[p], live_mag[p]);
        end
    endgenerate

    always @(posedge clk) begin
        if (rst) begin
            out_valid <= 1'b0;
            out_data  <= 16'd0;
        end else begin
            out_valid <= src_playback ? pb_valid : live_valid;
            out_data  <= src_playback ? pb_data : live_data;
        end
    end
endmodule
