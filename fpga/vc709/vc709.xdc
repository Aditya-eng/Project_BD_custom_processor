# Project BD on the VC709. Pin locations and I/O standards are copied from the Xilinx board
# definition (XilinxBoardStore, tag 2023.2, boards/Xilinx/vc709/1.8/part0_pins.xml,
# sha256 1c93d0b3061583ce...): PCIe x8 lanes and reference clock, PERST#, the 200 MHz
# system clock and the user LEDs.
# NOT YET BUILT: the first Vivado run must confirm the XDMA IP's PCIe block / GT placement
# agrees with these lane pins (a mismatch is a placement error, not a silent fault).

# ---- PCIe edge connector ----
set_property PACKAGE_PIN AB8 [get_ports pcie_refclk_p]
set_property PACKAGE_PIN AB7 [get_ports pcie_refclk_n]
create_clock -period 10.000 -name pcie_refclk [get_ports pcie_refclk_p]

set_property PACKAGE_PIN AV35 [get_ports pcie_perst_n]
set_property IOSTANDARD LVCMOS18 [get_ports pcie_perst_n]
set_property PULLUP true [get_ports pcie_perst_n]
set_false_path -from [get_ports pcie_perst_n]

set_property PACKAGE_PIN W2  [get_ports {pcie_txp[0]}]
set_property PACKAGE_PIN W1  [get_ports {pcie_txn[0]}]
set_property PACKAGE_PIN AA2 [get_ports {pcie_txp[1]}]
set_property PACKAGE_PIN AA1 [get_ports {pcie_txn[1]}]
set_property PACKAGE_PIN AC2 [get_ports {pcie_txp[2]}]
set_property PACKAGE_PIN AC1 [get_ports {pcie_txn[2]}]
set_property PACKAGE_PIN AE2 [get_ports {pcie_txp[3]}]
set_property PACKAGE_PIN AE1 [get_ports {pcie_txn[3]}]
set_property PACKAGE_PIN AG2 [get_ports {pcie_txp[4]}]
set_property PACKAGE_PIN AG1 [get_ports {pcie_txn[4]}]
set_property PACKAGE_PIN AH4 [get_ports {pcie_txp[5]}]
set_property PACKAGE_PIN AH3 [get_ports {pcie_txn[5]}]
set_property PACKAGE_PIN AJ2 [get_ports {pcie_txp[6]}]
set_property PACKAGE_PIN AJ1 [get_ports {pcie_txn[6]}]
set_property PACKAGE_PIN AK4 [get_ports {pcie_txp[7]}]
set_property PACKAGE_PIN AK3 [get_ports {pcie_txn[7]}]
set_property PACKAGE_PIN Y4  [get_ports {pcie_rxp[0]}]
set_property PACKAGE_PIN Y3  [get_ports {pcie_rxn[0]}]
set_property PACKAGE_PIN AA6 [get_ports {pcie_rxp[1]}]
set_property PACKAGE_PIN AA5 [get_ports {pcie_rxn[1]}]
set_property PACKAGE_PIN AB4 [get_ports {pcie_rxp[2]}]
set_property PACKAGE_PIN AB3 [get_ports {pcie_rxn[2]}]
set_property PACKAGE_PIN AC6 [get_ports {pcie_rxp[3]}]
set_property PACKAGE_PIN AC5 [get_ports {pcie_rxn[3]}]
set_property PACKAGE_PIN AD4 [get_ports {pcie_rxp[4]}]
set_property PACKAGE_PIN AD3 [get_ports {pcie_rxn[4]}]
set_property PACKAGE_PIN AE6 [get_ports {pcie_rxp[5]}]
set_property PACKAGE_PIN AE5 [get_ports {pcie_rxn[5]}]
set_property PACKAGE_PIN AF4 [get_ports {pcie_rxp[6]}]
set_property PACKAGE_PIN AF3 [get_ports {pcie_rxn[6]}]
set_property PACKAGE_PIN AG6 [get_ports {pcie_rxp[7]}]
set_property PACKAGE_PIN AG5 [get_ports {pcie_rxn[7]}]

# ---- 200 MHz system clock -> MMCM -> 79.5 MHz sample clock ----
set_property PACKAGE_PIN H19 [get_ports sysclk_p]
set_property PACKAGE_PIN G18 [get_ports sysclk_n]
set_property IOSTANDARD DIFF_SSTL15 [get_ports {sysclk_p sysclk_n}]
create_clock -period 5.000 -name sysclk [get_ports sysclk_p]

# ---- user LEDs ----
set_property PACKAGE_PIN AM39 [get_ports {led[0]}]
set_property PACKAGE_PIN AN39 [get_ports {led[1]}]
set_property PACKAGE_PIN AR37 [get_ports {led[2]}]
set_property PACKAGE_PIN AT37 [get_ports {led[3]}]
set_property PACKAGE_PIN AR35 [get_ports {led[4]}]
set_property PACKAGE_PIN AP41 [get_ports {led[5]}]
set_property PACKAGE_PIN AP42 [get_ports {led[6]}]
set_property PACKAGE_PIN AU39 [get_ports {led[7]}]
set_property IOSTANDARD LVCMOS18 [get_ports {led[*]}]
set_false_path -to [get_ports {led[*]}]

# ---- clock-domain crossings (bd_host_if) ----
# Every path between the PCIe user clock and the sample clock goes through a 2-FF
# synchronizer, a gray-coded FIFO pointer, or data held stable by a handshake/FIFO
# protocol. Limit them to one PCIe clock period of datapath delay (not unconstrained),
# so gray pointers cannot skew by more than a destination cycle.
set aclk  [get_clocks -of_objects [get_pins u_xdma/axi_aclk]]
set feclk [get_clocks -of_objects [get_pins u_mmcm/CLKOUT0]]
set_max_delay -datapath_only -from $aclk  -to $feclk 4.000
set_max_delay -datapath_only -from $feclk -to $aclk  4.000
