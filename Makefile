.PHONY: test test-model test-rtl test-sw build-sw lint lut lut-check estimate

RTL_CORE = bd_core.sv sample_mux.sv timebase.sv channel_bank.sv track_channel.sv

test: lut-check lint test-model test-rtl test-sw

test-model:
	python3 -m pytest -q model/tests

test-rtl:
	python3 -m pytest -q tb

build-sw:
	cmake -S sw -B sw/build -DCMAKE_BUILD_TYPE=Release
	cmake --build sw/build -j4

test-sw: build-sw
	cd sw/build && ctest --output-on-failure
	python3 -m pytest -q sw/tests

lint:
	cd rtl && verilator --lint-only -Wall track_channel.sv
	cd rtl && verilator --lint-only -Wall gps_ca_gen.sv
	cd rtl && verilator --lint-only -Wall --top-module bd_core $(RTL_CORE)
	cd rtl && verilator --lint-only -Wall -GNCH=192 --top-module bd_core $(RTL_CORE)

lut:
	python3 tools/gen_carrier_lut.py

lut-check:
	python3 tools/gen_carrier_lut.py --check

# Rough 7-series resource estimate (not a Vivado result). NCH defaults to 16.
NCH ?= 16
estimate:
	cd rtl && yosys -q -p "read_verilog -sv -I. $(RTL_CORE); chparam -set NCH $(NCH) bd_core; synth_xilinx -family xc7 -nodsp -top bd_core; stat"
