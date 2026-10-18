.PHONY: test test-model test-rtl lint lut

test: lut-check lint test-model test-rtl

test-model:
	python3 -m pytest -q model/tests

test-rtl:
	python3 -m pytest -q tb

lint:
	cd rtl && verilator --lint-only -Wall track_channel.sv && verilator --lint-only -Wall gps_ca_gen.sv

lut:
	python3 tools/gen_carrier_lut.py

lut-check:
	python3 tools/gen_carrier_lut.py --check

# Rough 7-series resource estimate (not a Vivado result).
estimate:
	cd rtl && yosys -q -p "read_verilog -sv -I. track_channel.sv; synth_xilinx -family xc7 -nodsp -top track_channel; stat"
