# Build the Project BD bitstream for the Xilinx VC709 (XC7VX690T-2FFG1761).
#
#   vivado -mode batch -source fpga/vc709/build.tcl -tclargs [NCH] [JOBS]
#
# NCH defaults to 192 (T2.1). Output: build/vc709/ (project, reports, bd_vc709.bit).
# Needs a Vivado licence that covers the XC7VX690T (Enterprise / device-locked; the free
# edition does not). The XDMA IP is generated here; its settings follow docs/ARCHITECTURE.md
# (Gen2 x8, AXI-Stream 128 bit at 250 MHz, one H2C + one C2H channel, 64 KB AXI-Lite BAR).
#
# NOT YET RUN: written without access to Vivado. Expect to adjust XDMA property names to
# the installed IP version on the first run (set_property stops with a clear error if a
# name differs). Gen2 x8 gives ~4 GB/s, ~25x what M2 needs (docs/RISKS.md R4).

set nch  [expr {[llength $argv] > 0 ? [lindex $argv 0] : 192}]
set jobs [expr {[llength $argv] > 1 ? [lindex $argv 1] : 8}]
set here [file dirname [file normalize [info script]]]
set root [file normalize [file join $here .. ..]]
set out  [file join $root build vc709]
file mkdir $out

create_project -force bd_vc709 $out -part xc7vx690tffg1761-2
set bp [lindex [lsort [get_board_parts -quiet *vc709*]] end]
if {$bp ne ""} {
    set_property board_part $bp [current_project]
} else {
    puts "WARNING: VC709 board files not installed; continuing with the bare part"
}

# ---- sources ----
foreach f [lsort [glob [file join $root rtl *.sv]]] {
    add_files -norecurse $f
}
add_files -norecurse [file join $here vc709_top.sv]
set_property include_dirs [list [file join $root rtl]] [current_fileset]
set_property file_type SystemVerilog [get_files *.sv]
add_files -fileset constrs_1 -norecurse [file join $here vc709.xdc]
set_property top vc709_top [current_fileset]
set_property generic "NCH=$nch" [current_fileset]

# ---- XDMA PCIe endpoint ----
create_ip -name xdma -vendor xilinx.com -library ip -module_name xdma_0
set_property -dict [list \
    CONFIG.mode_selection             {Advanced} \
    CONFIG.pl_link_cap_max_link_width {X8} \
    CONFIG.pl_link_cap_max_link_speed {5.0_GT/s} \
    CONFIG.ref_clk_freq               {100_MHz} \
    CONFIG.axi_data_width             {128_bit} \
    CONFIG.axisten_freq               {250} \
    CONFIG.xdma_axi_intf_mm           {AXI_Stream} \
    CONFIG.xdma_rnum_chnl             {1} \
    CONFIG.xdma_wnum_chnl             {1} \
    CONFIG.axilite_master_en          {true} \
    CONFIG.axilite_master_size        {64} \
    CONFIG.axilite_master_scale       {Kilobytes} \
] [get_ips xdma_0]
if {$bp ne ""} {
    # Lets the IP take its GT placement from the board definition where supported.
    if {[catch {set_property CONFIG.PCIE_BOARD_INTERFACE {pci_express_x8} [get_ips xdma_0]} e]} {
        puts "NOTE: PCIE_BOARD_INTERFACE not settable ($e); lane pins come from vc709.xdc"
    }
}
generate_target all [get_ips xdma_0]

# ---- synthesis, implementation, bitstream ----
launch_runs synth_1 -jobs $jobs
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} { error "synthesis failed" }
launch_runs impl_1 -to_step write_bitstream -jobs $jobs
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} { error "implementation failed" }

open_run impl_1
report_utilization    -file [file join $out utilization_nch$nch.rpt]
report_timing_summary -file [file join $out timing_nch$nch.rpt] -max_paths 20
report_cdc            -file [file join $out cdc_nch$nch.rpt]
file copy -force [glob [file join $out bd_vc709.runs impl_1 *.bit]] [file join $out bd_vc709.bit]

set wns [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -setup]]
puts "NCH=$nch  WNS=$wns ns  (T2.1 passes with WNS >= 0)"
if {$wns < 0} { error "timing not met" }
