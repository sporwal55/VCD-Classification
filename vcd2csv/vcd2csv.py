#!/usr/bin/env python2

import sys
import csv
from Verilog_VCD import *

def computeHamming(a, b):
	distance = 0
	while(a != 0 or b != 0):
		if (a % 2) != (b % 2):
			distance += 1
		a >>= 1
		b >>= 1
	return distance


if len(sys.argv) != 4:
	print("Usage: " + sys.argv[0] + " <vcd file> <txt file with target signal names> <output csv name>")
	exit()

vcd_fname = sys.argv[1]
sig_fname = sys.argv[2]
out_fname = sys.argv[3]

sigs = []
sig_ranges = {}
found_clock = False
with open(sig_fname, "r") as sig_f:
	for line in sig_f:
		split_line = line.strip().split()
		sig = split_line[0]
		sigs.append(sig)
		if len(split_line) == 2 and split_line[-1] == "CLOCK": # Found clock signal
			if not found_clock:
				found_clock = True
				clock_name = sig
				print("Found clock signal " + sig)
			else:
				print("ERROR: Found multiple clocks in signal list")
				exit()
			continue
		if len(split_line) > 1: # Get specified bit ranges for signal
			sig_ranges.update({sig : []})
			for sig_range in split_line[1:]:
				if sig_range[0] == "[":
					if sig_range[-1] != "]":
						print("ERROR: Incompletely specified range for signal " + sig)
						exit()
					else:
						sig_ranges[sig].append((int(sig_range[1:].split(":")[0]), int(sig_range[:-1].split(":")[1])))
				else:
					sig_ranges[sig].append((int(sig_range), int(sig_range)))
				if sig_ranges[sig][-1][0] < sig_ranges[sig][-1][1]:
					print("ERROR: Illegal range for signal " + sig + ": [" + sig_ranges[sig][-1][0] + ":" + sig_ranges[sig][-1][1] + "]")
if not found_clock:
	print("ERROR: Didn't find clock signal")
	exit()

# Move clock signal to start of list
sigs.remove(clock_name)
sigs.insert(0, clock_name)

print("List of signals to extract: " + str(sigs))

vcd = parse_vcd(vcd_fname, siglist=sigs)
print("Read in VCD")

# Construct a mapping from full signal names to the abbreviated variable name used in the VCD
fullname_mappings = {}
for varname, data in vcd.iteritems():
	for net in data["nets"]:
		fullname = net["hier"] + "." + net["name"]
		fullname_mappings.update({fullname : varname})

# Assumptions: Clock period is constant, and there is at most one entry for the clock before it stabilizes
clock_data = vcd[fullname_mappings[clock_name]]["tv"]
first_posedge_idx = None
first_posedge_time = None
for entry_idx, entry in enumerate(clock_data):
	if int(entry[1]) == 1:
		first_posedge_idx = entry_idx
		first_posedge_time = entry[0]
		break
if first_posedge_time is None:
	print("ERROR: Could not find rising clock edge")
	exit()
clock_period = clock_data[first_posedge_idx+2][0] - first_posedge_time
print("clock period " + str(clock_period))

xz_count = 0
sigs_trace = {}
max_clock = 0
for sig in sigs[1:]:
	sigs_trace.update({sig : []})
	sig_data= vcd[fullname_mappings[sig]]["tv"]
	current_time = first_posedge_time
	current_clock = 0
	entry_idx = 0
	while entry_idx < len(sig_data)-1:
		while entry_idx < len(sig_data)-1 and sig_data[entry_idx+1][0] <= current_time:
			entry_idx += 1
		sig_entry = bytearray(sig_data[entry_idx][1])
		for char_idx in range(len(sig_entry)):
			if sig_entry[char_idx] == ord('x') or sig_entry[char_idx] == ord('z'):
				sig_entry[char_idx] = ord('0')
				xz_count += 1
		sigs_trace[sig].append(int(str(sig_entry), 2))
		if entry_idx < len(sig_data)-1:
			current_clock += 1
			if current_clock > max_clock:
				max_clock = current_clock
			current_time += clock_period
	if len(sigs_trace[sig]) == 0:
		sigs_trace[sig].append(int(sig_data[-1][1], 2))
for sig in sigs[1:]: # Expand out shorter signal traces with their final value

	while len(sigs_trace[sig]) < max_clock + 1:
		sigs_trace[sig].append(sigs_trace[sig][-1])

if xz_count > 0:
	print("WARNING: " + str(xz_count) + " undefined or high-impedance signal values were encountered in signal data")

# Write results to file

out_file = open(out_fname, "wb")
out_writer = csv.writer(out_file, delimiter=",")

header = ["Cycle", "Global_Distance"]
for sig in sigs[1:]:
	if sig not in sig_ranges:
		header.append(sig)
		header.append("d_" + sig)
	else:
		for sig_range in sig_ranges[sig]:
			sig_name = sig + "[" + str(sig_range[0]) + ":" + str(sig_range[1]) + "]"
			header.append(sig_name)
			header.append("d_" + sig_name)
out_writer.writerow(header)
for i in range(max_clock + 1):
	line = [i]
	if i == 0:
		line.append(0)
	else: # Compute Hamming distance from the previous line
		distance = 0
		for sig in sigs[1:]:
			last_val = sigs_trace[sig][i-1]
			curr_val = sigs_trace[sig][i]
			distance += computeHamming(last_val, curr_val)
		line.append(distance)
	for sig in sigs[1:]:
		if sig not in sig_ranges:
			line.append(sigs_trace[sig][i])
			if i == 0:
				line.append(0)
			else:
				line.append(computeHamming(sigs_trace[sig][i-1], sigs_trace[sig][i]))
		else:
			for sig_range in sig_ranges[sig]:
				bits_in_range = 1 + sig_range[0] - sig_range[1]
				masked_bits = sigs_trace[sig][i] >> sig_range[1]
				masked_bits &= (1 << bits_in_range) - 1
				line.append(masked_bits)
				if i == 0:
					line.append(0)
				else:
					last_masked_bits = sigs_trace[sig][i-1] >> sig_range[1]
					last_masked_bits &= (1 << bits_in_range) - 1
					line.append(computeHamming(last_masked_bits, masked_bits))
	out_writer.writerow(line)
