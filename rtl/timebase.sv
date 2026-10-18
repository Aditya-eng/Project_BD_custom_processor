// Receiver timebase in the sample domain.
//
// sample_cnt is the index of the sample currently on the bus (number of
// valid samples before it). Measurement tics and the PPS output fire on
// absolute sample counts that the host programs, so the host aligns both to
// GPS time to one-sample resolution without any hardware time arithmetic.
module timebase (
    input  wire        clk,
    input  wire        rst,
    input  wire        sample_valid,

    // Measurement tic: fires on the sample whose index == tic_next, then
    // tic_next += tic_period. tic_period == 0 disables.
    input  wire [31:0] tic_period,
    input  wire        tic_next_wr,
    input  wire [63:0] tic_next_in,
    output wire        tic,
    output reg  [63:0] last_tic_cnt,

    // PPS: registered output that rises one clock after the sample with
    // index pps_next and stays high for pps_width samples; then
    // pps_next = that index + pps_period. pps_period == 0 disables re-arming.
    input  wire [31:0] pps_period,
    input  wire [31:0] pps_width,
    input  wire        pps_next_wr,
    input  wire [63:0] pps_next_in,
    output reg         pps_out,

    // Event input (asynchronous): a rising edge is stamped with the sample
    // index current two clocks after it is first sampled (2-FF synchronizer);
    // the host subtracts this fixed latency.
    input  wire        event_in,
    output reg  [63:0] event_cnt,
    output reg  [31:0] event_count,

    output reg  [63:0] sample_cnt
);
    reg [63:0] tic_next, pps_next, pps_off;
    reg        tic_armed, pps_armed;

    assign tic = sample_valid && tic_armed && (sample_cnt == tic_next);
    wire pps_hit = sample_valid && pps_armed && (sample_cnt == pps_next);
    wire pps_end = sample_valid && pps_out && (sample_cnt == pps_off);

    reg [2:0] ev_sync;
    wire ev_rise = ev_sync[1] && !ev_sync[2];

    always @(posedge clk) begin
        if (rst) begin
            sample_cnt   <= 64'd0;
            tic_next     <= 64'd0;
            tic_armed    <= 1'b0;
            last_tic_cnt <= 64'd0;
            pps_next     <= 64'd0;
            pps_off      <= 64'd0;
            pps_armed    <= 1'b0;
            pps_out      <= 1'b0;
            ev_sync      <= 3'b000;
            event_cnt    <= 64'd0;
            event_count  <= 32'd0;
        end else begin
            if (sample_valid)
                sample_cnt <= sample_cnt + 1'b1;

            if (tic)
                last_tic_cnt <= sample_cnt;
            if (tic_next_wr) begin
                tic_next  <= tic_next_in;
                tic_armed <= 1'b1;
            end else if (tic) begin
                tic_next  <= tic_next + {32'd0, tic_period};
                tic_armed <= tic_period != 0;
            end

            if (pps_end)
                pps_out <= 1'b0;
            if (pps_next_wr) begin
                pps_next  <= pps_next_in;
                pps_armed <= 1'b1;
            end else if (pps_hit) begin
                pps_out   <= pps_width != 0;
                pps_off   <= sample_cnt + {32'd0, pps_width};
                pps_next  <= sample_cnt + {32'd0, pps_period};
                pps_armed <= pps_period != 0;
            end

            ev_sync <= {ev_sync[1:0], event_in};
            if (ev_rise) begin
                event_cnt   <= sample_cnt;
                event_count <= event_count + 1'b1;
            end
        end
    end
endmodule
