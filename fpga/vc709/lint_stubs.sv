// Port-only stand-ins for the Xilinx primitives and the generated XDMA IP, so Verilator can
// lint vc709_top's own wiring (make lint). They are never synthesized. The xdma_0 port list
// is our reading of the XDMA product guide (PG195) for a 7-series AXI-Stream configuration;
// the first Vivado build confirms it against the generated IP.
/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off UNDRIVEN */
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off DECLFILENAME */
module xdma_0 (
    input  wire         sys_clk, sys_rst_n,
    output wire         user_lnk_up,
    output wire [7:0]   pci_exp_txp, pci_exp_txn,
    input  wire [7:0]   pci_exp_rxp, pci_exp_rxn,
    output wire         axi_aclk, axi_aresetn,
    input  wire [0:0]   usr_irq_req,
    output wire [0:0]   usr_irq_ack,
    output wire         msi_enable,
    output wire [2:0]   msi_vector_width,
    output wire [31:0]  m_axil_awaddr, m_axil_araddr, m_axil_wdata,
    output wire [2:0]   m_axil_awprot, m_axil_arprot,
    output wire [3:0]   m_axil_wstrb,
    output wire         m_axil_awvalid, m_axil_wvalid, m_axil_bready, m_axil_arvalid,
                        m_axil_rready,
    input  wire         m_axil_awready, m_axil_wready, m_axil_bvalid, m_axil_arready,
                        m_axil_rvalid,
    input  wire [1:0]   m_axil_bresp, m_axil_rresp,
    input  wire [31:0]  m_axil_rdata,
    output wire [127:0] m_axis_h2c_tdata_0,
    output wire [15:0]  m_axis_h2c_tkeep_0,
    output wire         m_axis_h2c_tlast_0, m_axis_h2c_tvalid_0,
    input  wire         m_axis_h2c_tready_0,
    input  wire [127:0] s_axis_c2h_tdata_0,
    input  wire [15:0]  s_axis_c2h_tkeep_0,
    input  wire         s_axis_c2h_tlast_0, s_axis_c2h_tvalid_0,
    output wire         s_axis_c2h_tready_0
);
endmodule

module IBUFDS_GTE2 (input wire I, IB, CEB, output wire O, ODIV2);
endmodule

module IBUFDS #(parameter DIFF_TERM = "FALSE") (input wire I, IB, output wire O);
endmodule

module BUFG (input wire I, output wire O);
endmodule

module MMCME2_BASE #(
    parameter real CLKIN1_PERIOD = 0.0,
    parameter integer DIVCLK_DIVIDE = 1,
    parameter real CLKFBOUT_MULT_F = 5.0,
    parameter real CLKOUT0_DIVIDE_F = 1.0
) (
    input  wire CLKIN1, CLKFBIN, RST, PWRDWN,
    output wire CLKFBOUT, CLKFBOUTB, CLKOUT0, CLKOUT0B, CLKOUT1, CLKOUT1B, CLKOUT2, CLKOUT2B,
                CLKOUT3, CLKOUT3B, CLKOUT4, CLKOUT5, CLKOUT6, LOCKED
);
endmodule
/* verilator lint_on DECLFILENAME */
/* verilator lint_on UNUSEDPARAM */
/* verilator lint_on UNDRIVEN */
/* verilator lint_on UNUSEDSIGNAL */
