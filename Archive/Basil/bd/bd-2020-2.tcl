
################################################################
# This is a generated script based on design: d_1
#
# Though there are limitations about the generated script,
# the main purpose of this utility is to make learning
# IP Integrator Tcl commands easier.
################################################################

namespace eval _tcl {
proc get_script_folder {} {
   set script_path [file normalize [info script]]
   set script_folder [file dirname $script_path]
   return $script_folder
}
}
variable script_folder
set script_folder [_tcl::get_script_folder]

################################################################
# Check if script is running in correct Vivado version.
################################################################
set scripts_vivado_version 2020.2
set current_vivado_version [version -short]

if { [string first $scripts_vivado_version $current_vivado_version] == -1 } {
   puts ""
   catch {common::send_gid_msg -ssname BD::TCL -id 2041 -severity "ERROR" "This script was generated using Vivado <$scripts_vivado_version> and is being run in <$current_vivado_version> of Vivado. Please run the script in Vivado <$scripts_vivado_version> then open the design in Vivado <$current_vivado_version>. Upgrade the design by running \"Tools => Report => Report IP Status...\", then run write_bd_tcl to create an updated script."}

   return 1
}

################################################################
# START
################################################################

# To test this script, run the following commands from Vivado Tcl console:
# source d_1_script.tcl


# The design that will be created by this Tcl script contains the following 
# module references:
# vect2bits_9

# Please add the sources of those modules before sourcing this Tcl script.

# If there is no project opened, this script will create a
# project, but make sure you do not have an existing project
# <./myproj/project_1.xpr> in the current working folder.

set list_projs [get_projects -quiet]
if { $list_projs eq "" } {
   create_project project_1 myproj -part xczu49dr-ffvf1760-2-e
   set_property BOARD_PART xilinx.com:zcu216:part0:2.0 [current_project]
}


# CHANGE DESIGN NAME HERE
variable design_name
set design_name d_1

# If you do not already have an existing IP Integrator design open,
# you can create a design using the following command:
#    create_bd_design $design_name

# Creating design if needed
set errMsg ""
set nRet 0

set cur_design [current_bd_design -quiet]
set list_cells [get_bd_cells -quiet]

if { ${design_name} eq "" } {
   # USE CASES:
   #    1) Design_name not set

   set errMsg "Please set the variable <design_name> to a non-empty value."
   set nRet 1

} elseif { ${cur_design} ne "" && ${list_cells} eq "" } {
   # USE CASES:
   #    2): Current design opened AND is empty AND names same.
   #    3): Current design opened AND is empty AND names diff; design_name NOT in project.
   #    4): Current design opened AND is empty AND names diff; design_name exists in project.

   if { $cur_design ne $design_name } {
      common::send_gid_msg -ssname BD::TCL -id 2001 -severity "INFO" "Changing value of <design_name> from <$design_name> to <$cur_design> since current design is empty."
      set design_name [get_property NAME $cur_design]
   }
   common::send_gid_msg -ssname BD::TCL -id 2002 -severity "INFO" "Constructing design in IPI design <$cur_design>..."

} elseif { ${cur_design} ne "" && $list_cells ne "" && $cur_design eq $design_name } {
   # USE CASES:
   #    5) Current design opened AND has components AND same names.

   set errMsg "Design <$design_name> already exists in your project, please set the variable <design_name> to another value."
   set nRet 1
} elseif { [get_files -quiet ${design_name}.bd] ne "" } {
   # USE CASES: 
   #    6) Current opened design, has components, but diff names, design_name exists in project.
   #    7) No opened design, design_name exists in project.

   set errMsg "Design <$design_name> already exists in your project, please set the variable <design_name> to another value."
   set nRet 2

} else {
   # USE CASES:
   #    8) No opened design, design_name not in project.
   #    9) Current opened design, has components, but diff names, design_name not in project.

   common::send_gid_msg -ssname BD::TCL -id 2003 -severity "INFO" "Currently there is no design <$design_name> in project, so creating one..."

   create_bd_design $design_name

   common::send_gid_msg -ssname BD::TCL -id 2004 -severity "INFO" "Making design <$design_name> as current_bd_design."
   current_bd_design $design_name

}

common::send_gid_msg -ssname BD::TCL -id 2005 -severity "INFO" "Currently the variable <design_name> is equal to \"$design_name\"."

if { $nRet != 0 } {
   catch {common::send_gid_msg -ssname BD::TCL -id 2006 -severity "ERROR" $errMsg}
   return $nRet
}

set bCheckIPsPassed 1
##################################################################
# CHECK IPs
##################################################################
set bCheckIPs 1
if { $bCheckIPs == 1 } {
   set list_check_ips "\ 
xilinx.com:ip:axi_bram_ctrl:4.1\
xilinx.com:ip:blk_mem_gen:8.4\
xilinx.com:ip:axi_dma:7.1\
xilinx.com:ip:smartconnect:1.0\
user.org:user:axis_avg_buffer:1.0\
xilinx.com:ip:axis_clock_converter:1.1\
user.org:user:axis_constant_iq:1.0\
user.org:user:axis_pfb_readout_v2:1.0\
user.org:user:axis_register_slice_nb:1.0\
user.org:user:axis_set_reg:1.0\
user.org:user:axis_sg_int4_v1:1.0\
user.org:user:axis_sg_mux4_v2:1.0\
user.org:user:axis_signal_gen_v6:1.0\
xilinx.com:ip:axis_switch:1.1\
user.org:user:axis_tproc64x32_x8:1.0\
xilinx.com:ip:clk_wiz:6.0\
xilinx.com:ip:proc_sys_reset:5.0\
xilinx.com:ip:usp_rf_data_converter:2.4\
xilinx.com:ip:xlconstant:1.1\
xilinx.com:ip:zynq_ultra_ps_e:3.3\
"

   set list_ips_missing ""
   common::send_gid_msg -ssname BD::TCL -id 2011 -severity "INFO" "Checking if the following IPs exist in the project's IP catalog: $list_check_ips ."

   foreach ip_vlnv $list_check_ips {
      set ip_obj [get_ipdefs -all $ip_vlnv]
      if { $ip_obj eq "" } {
         lappend list_ips_missing $ip_vlnv
      }
   }

   if { $list_ips_missing ne "" } {
      catch {common::send_gid_msg -ssname BD::TCL -id 2012 -severity "ERROR" "The following IPs are not found in the IP Catalog:\n  $list_ips_missing\n\nResolution: Please add the repository containing the IP(s) to the project." }
      set bCheckIPsPassed 0
   }

}

##################################################################
# CHECK Modules
##################################################################
set bCheckModules 1
if { $bCheckModules == 1 } {
   set list_check_mods "\ 
vect2bits_9\
"

   set list_mods_missing ""
   common::send_gid_msg -ssname BD::TCL -id 2020 -severity "INFO" "Checking if the following modules exist in the project's sources: $list_check_mods ."

   foreach mod_vlnv $list_check_mods {
      if { [can_resolve_reference $mod_vlnv] == 0 } {
         lappend list_mods_missing $mod_vlnv
      }
   }

   if { $list_mods_missing ne "" } {
      catch {common::send_gid_msg -ssname BD::TCL -id 2021 -severity "ERROR" "The following module(s) are not found in the project: $list_mods_missing" }
      common::send_gid_msg -ssname BD::TCL -id 2022 -severity "INFO" "Please add source files for the missing module(s) above."
      set bCheckIPsPassed 0
   }
}

if { $bCheckIPsPassed != 1 } {
  common::send_gid_msg -ssname BD::TCL -id 2023 -severity "WARNING" "Will not continue with creation of design due to the error(s) above."
  return 3
}

##################################################################
# DESIGN PROCs
##################################################################



# Procedure to create entire design; Provide argument to make
# procedure reusable. If parentCell is "", will use root.
proc create_root_design { parentCell } {

  variable script_folder
  variable design_name

  if { $parentCell eq "" } {
     set parentCell [get_bd_cells /]
  }

  # Get object for parentCell
  set parentObj [get_bd_cells $parentCell]
  if { $parentObj == "" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2090 -severity "ERROR" "Unable to find parent cell <$parentCell>!"}
     return
  }

  # Make sure parentObj is hier blk
  set parentType [get_property TYPE $parentObj]
  if { $parentType ne "hier" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2091 -severity "ERROR" "Parent <$parentObj> has TYPE = <$parentType>. Expected to be <hier>."}
     return
  }

  # Save current instance; Restore later
  set oldCurInst [current_bd_instance .]

  # Set parent object as current
  current_bd_instance $parentObj


  # Create interface ports
  set adc2_clk [ create_bd_intf_port -mode Slave -vlnv xilinx.com:interface:diff_clock_rtl:1.0 adc2_clk ]

  set dac2_clk [ create_bd_intf_port -mode Slave -vlnv xilinx.com:interface:diff_clock_rtl:1.0 dac2_clk ]

  set sysref_in [ create_bd_intf_port -mode Slave -vlnv xilinx.com:display_usp_rf_data_converter:diff_pins_rtl:1.0 sysref_in ]

  set vin20 [ create_bd_intf_port -mode Slave -vlnv xilinx.com:interface:diff_analog_io_rtl:1.0 vin20 ]

  set vout00 [ create_bd_intf_port -mode Master -vlnv xilinx.com:interface:diff_analog_io_rtl:1.0 vout00 ]

  set vout10 [ create_bd_intf_port -mode Master -vlnv xilinx.com:interface:diff_analog_io_rtl:1.0 vout10 ]

  set vout11 [ create_bd_intf_port -mode Master -vlnv xilinx.com:interface:diff_analog_io_rtl:1.0 vout11 ]

  set vout12 [ create_bd_intf_port -mode Master -vlnv xilinx.com:interface:diff_analog_io_rtl:1.0 vout12 ]

  set vout13 [ create_bd_intf_port -mode Master -vlnv xilinx.com:interface:diff_analog_io_rtl:1.0 vout13 ]

  set vout20 [ create_bd_intf_port -mode Master -vlnv xilinx.com:interface:diff_analog_io_rtl:1.0 vout20 ]

  set vout21 [ create_bd_intf_port -mode Master -vlnv xilinx.com:interface:diff_analog_io_rtl:1.0 vout21 ]

  set vout22 [ create_bd_intf_port -mode Master -vlnv xilinx.com:interface:diff_analog_io_rtl:1.0 vout22 ]

  set vout23 [ create_bd_intf_port -mode Master -vlnv xilinx.com:interface:diff_analog_io_rtl:1.0 vout23 ]

  set vout30 [ create_bd_intf_port -mode Master -vlnv xilinx.com:interface:diff_analog_io_rtl:1.0 vout30 ]

  set vout31 [ create_bd_intf_port -mode Master -vlnv xilinx.com:interface:diff_analog_io_rtl:1.0 vout31 ]


  # Create ports
  set PMOD0_0_LS [ create_bd_port -dir O PMOD0_0_LS ]
  set PMOD0_1_LS [ create_bd_port -dir O PMOD0_1_LS ]
  set PMOD0_2_LS [ create_bd_port -dir O PMOD0_2_LS ]
  set PMOD0_3_LS [ create_bd_port -dir O PMOD0_3_LS ]
  set PMOD1_0_LS [ create_bd_port -dir I PMOD1_0_LS ]

  # Create instance: axi_bram_ctrl_0, and set properties
  set axi_bram_ctrl_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_bram_ctrl:4.1 axi_bram_ctrl_0 ]
  set_property -dict [ list \
   CONFIG.DATA_WIDTH {64} \
   CONFIG.ECC_TYPE {0} \
   CONFIG.SINGLE_PORT_BRAM {1} \
 ] $axi_bram_ctrl_0

  # Create instance: axi_bram_ctrl_0_bram, and set properties
  set axi_bram_ctrl_0_bram [ create_bd_cell -type ip -vlnv xilinx.com:ip:blk_mem_gen:8.4 axi_bram_ctrl_0_bram ]
  set_property -dict [ list \
   CONFIG.EN_SAFETY_CKT {false} \
   CONFIG.Memory_Type {True_Dual_Port_RAM} \
   CONFIG.Read_Width_B {64} \
   CONFIG.Write_Width_B {64} \
 ] $axi_bram_ctrl_0_bram

  # Create instance: axi_dma_avg, and set properties
  set axi_dma_avg [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:7.1 axi_dma_avg ]
  set_property -dict [ list \
   CONFIG.c_include_mm2s {0} \
   CONFIG.c_include_sg {0} \
   CONFIG.c_sg_include_stscntrl_strm {0} \
   CONFIG.c_sg_length_width {26} \
 ] $axi_dma_avg

  # Create instance: axi_dma_buf, and set properties
  set axi_dma_buf [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:7.1 axi_dma_buf ]
  set_property -dict [ list \
   CONFIG.c_include_mm2s {0} \
   CONFIG.c_include_sg {0} \
   CONFIG.c_sg_include_stscntrl_strm {0} \
   CONFIG.c_sg_length_width {26} \
 ] $axi_dma_buf

  # Create instance: axi_dma_gen, and set properties
  set axi_dma_gen [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:7.1 axi_dma_gen ]
  set_property -dict [ list \
   CONFIG.c_include_s2mm {0} \
   CONFIG.c_include_sg {0} \
   CONFIG.c_sg_include_stscntrl_strm {0} \
   CONFIG.c_sg_length_width {26} \
 ] $axi_dma_gen

  # Create instance: axi_dma_tproc, and set properties
  set axi_dma_tproc [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:7.1 axi_dma_tproc ]
  set_property -dict [ list \
   CONFIG.c_include_sg {0} \
   CONFIG.c_sg_include_stscntrl_strm {0} \
   CONFIG.c_sg_length_width {26} \
 ] $axi_dma_tproc

  # Create instance: axi_smc, and set properties
  set axi_smc [ create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 axi_smc ]
  set_property -dict [ list \
   CONFIG.NUM_MI {16} \
   CONFIG.NUM_SI {1} \
 ] $axi_smc

  # Create instance: axi_smc_1, and set properties
  set axi_smc_1 [ create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 axi_smc_1 ]
  set_property -dict [ list \
   CONFIG.NUM_SI {3} \
 ] $axi_smc_1

  # Create instance: axi_smc_2, and set properties
  set axi_smc_2 [ create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 axi_smc_2 ]
  set_property -dict [ list \
   CONFIG.NUM_SI {2} \
 ] $axi_smc_2

  # Create instance: axis_avg_buffer_0, and set properties
  set axis_avg_buffer_0 [ create_bd_cell -type ip -vlnv user.org:user:axis_avg_buffer:1.0 axis_avg_buffer_0 ]

  # Create instance: axis_avg_buffer_1, and set properties
  set axis_avg_buffer_1 [ create_bd_cell -type ip -vlnv user.org:user:axis_avg_buffer:1.0 axis_avg_buffer_1 ]

  # Create instance: axis_avg_buffer_2, and set properties
  set axis_avg_buffer_2 [ create_bd_cell -type ip -vlnv user.org:user:axis_avg_buffer:1.0 axis_avg_buffer_2 ]

  # Create instance: axis_avg_buffer_3, and set properties
  set axis_avg_buffer_3 [ create_bd_cell -type ip -vlnv user.org:user:axis_avg_buffer:1.0 axis_avg_buffer_3 ]

  # Create instance: axis_cc_avg_0, and set properties
  set axis_cc_avg_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:axis_clock_converter:1.1 axis_cc_avg_0 ]

  # Create instance: axis_cc_avg_1, and set properties
  set axis_cc_avg_1 [ create_bd_cell -type ip -vlnv xilinx.com:ip:axis_clock_converter:1.1 axis_cc_avg_1 ]

  # Create instance: axis_cc_avg_2, and set properties
  set axis_cc_avg_2 [ create_bd_cell -type ip -vlnv xilinx.com:ip:axis_clock_converter:1.1 axis_cc_avg_2 ]

  # Create instance: axis_cc_avg_3, and set properties
  set axis_cc_avg_3 [ create_bd_cell -type ip -vlnv xilinx.com:ip:axis_clock_converter:1.1 axis_cc_avg_3 ]

  # Create instance: axis_cc_sg_0, and set properties
  set axis_cc_sg_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:axis_clock_converter:1.1 axis_cc_sg_0 ]

  # Create instance: axis_cc_sg_1, and set properties
  set axis_cc_sg_1 [ create_bd_cell -type ip -vlnv xilinx.com:ip:axis_clock_converter:1.1 axis_cc_sg_1 ]

  # Create instance: axis_cc_sg_2, and set properties
  set axis_cc_sg_2 [ create_bd_cell -type ip -vlnv xilinx.com:ip:axis_clock_converter:1.1 axis_cc_sg_2 ]

  # Create instance: axis_cc_sg_3, and set properties
  set axis_cc_sg_3 [ create_bd_cell -type ip -vlnv xilinx.com:ip:axis_clock_converter:1.1 axis_cc_sg_3 ]

  # Create instance: axis_cc_sg_4, and set properties
  set axis_cc_sg_4 [ create_bd_cell -type ip -vlnv xilinx.com:ip:axis_clock_converter:1.1 axis_cc_sg_4 ]

  # Create instance: axis_cc_sg_5, and set properties
  set axis_cc_sg_5 [ create_bd_cell -type ip -vlnv xilinx.com:ip:axis_clock_converter:1.1 axis_cc_sg_5 ]

  # Create instance: axis_cc_sg_6, and set properties
  set axis_cc_sg_6 [ create_bd_cell -type ip -vlnv xilinx.com:ip:axis_clock_converter:1.1 axis_cc_sg_6 ]

  # Create instance: axis_constant_iq_0, and set properties
  set axis_constant_iq_0 [ create_bd_cell -type ip -vlnv user.org:user:axis_constant_iq:1.0 axis_constant_iq_0 ]
  set_property -dict [ list \
   CONFIG.N {8} \
 ] $axis_constant_iq_0

  # Create instance: axis_constant_iq_1, and set properties
  set axis_constant_iq_1 [ create_bd_cell -type ip -vlnv user.org:user:axis_constant_iq:1.0 axis_constant_iq_1 ]
  set_property -dict [ list \
   CONFIG.N {8} \
 ] $axis_constant_iq_1

  # Create instance: axis_constant_iq_2, and set properties
  set axis_constant_iq_2 [ create_bd_cell -type ip -vlnv user.org:user:axis_constant_iq:1.0 axis_constant_iq_2 ]
  set_property -dict [ list \
   CONFIG.N {8} \
 ] $axis_constant_iq_2

  # Create instance: axis_constant_iq_3, and set properties
  set axis_constant_iq_3 [ create_bd_cell -type ip -vlnv user.org:user:axis_constant_iq:1.0 axis_constant_iq_3 ]
  set_property -dict [ list \
   CONFIG.N {8} \
 ] $axis_constant_iq_3

  # Create instance: axis_pfb_readout_v2_0, and set properties
  set axis_pfb_readout_v2_0 [ create_bd_cell -type ip -vlnv user.org:user:axis_pfb_readout_v2:1.0 axis_pfb_readout_v2_0 ]

  # Create instance: axis_register_slice_0, and set properties
  set axis_register_slice_0 [ create_bd_cell -type ip -vlnv user.org:user:axis_register_slice_nb:1.0 axis_register_slice_0 ]
  set_property -dict [ list \
   CONFIG.B {256} \
 ] $axis_register_slice_0

  # Create instance: axis_register_slice_1, and set properties
  set axis_register_slice_1 [ create_bd_cell -type ip -vlnv user.org:user:axis_register_slice_nb:1.0 axis_register_slice_1 ]
  set_property -dict [ list \
   CONFIG.B {256} \
 ] $axis_register_slice_1

  # Create instance: axis_set_reg_0, and set properties
  set axis_set_reg_0 [ create_bd_cell -type ip -vlnv user.org:user:axis_set_reg:1.0 axis_set_reg_0 ]
  set_property -dict [ list \
   CONFIG.DATA_WIDTH {160} \
 ] $axis_set_reg_0

  # Create instance: axis_sg_int4_v1_0, and set properties
  set axis_sg_int4_v1_0 [ create_bd_cell -type ip -vlnv user.org:user:axis_sg_int4_v1:1.0 axis_sg_int4_v1_0 ]

  # Create instance: axis_sg_int4_v1_1, and set properties
  set axis_sg_int4_v1_1 [ create_bd_cell -type ip -vlnv user.org:user:axis_sg_int4_v1:1.0 axis_sg_int4_v1_1 ]

  # Create instance: axis_sg_int4_v1_2, and set properties
  set axis_sg_int4_v1_2 [ create_bd_cell -type ip -vlnv user.org:user:axis_sg_int4_v1:1.0 axis_sg_int4_v1_2 ]

  # Create instance: axis_sg_int4_v1_3, and set properties
  set axis_sg_int4_v1_3 [ create_bd_cell -type ip -vlnv user.org:user:axis_sg_int4_v1:1.0 axis_sg_int4_v1_3 ]

  # Create instance: axis_sg_mux4_v2_6, and set properties
  set axis_sg_mux4_v2_6 [ create_bd_cell -type ip -vlnv user.org:user:axis_sg_mux4_v2:1.0 axis_sg_mux4_v2_6 ]
  set_property -dict [ list \
   CONFIG.N_DDS {4} \
 ] $axis_sg_mux4_v2_6

  # Create instance: axis_signal_gen_v6_4, and set properties
  set axis_signal_gen_v6_4 [ create_bd_cell -type ip -vlnv user.org:user:axis_signal_gen_v6:1.0 axis_signal_gen_v6_4 ]

  # Create instance: axis_signal_gen_v6_5, and set properties
  set axis_signal_gen_v6_5 [ create_bd_cell -type ip -vlnv user.org:user:axis_signal_gen_v6:1.0 axis_signal_gen_v6_5 ]

  # Create instance: axis_switch_avg, and set properties
  set axis_switch_avg [ create_bd_cell -type ip -vlnv xilinx.com:ip:axis_switch:1.1 axis_switch_avg ]
  set_property -dict [ list \
   CONFIG.NUM_SI {4} \
   CONFIG.ROUTING_MODE {1} \
 ] $axis_switch_avg

  # Create instance: axis_switch_buf, and set properties
  set axis_switch_buf [ create_bd_cell -type ip -vlnv xilinx.com:ip:axis_switch:1.1 axis_switch_buf ]
  set_property -dict [ list \
   CONFIG.NUM_SI {4} \
   CONFIG.ROUTING_MODE {1} \
 ] $axis_switch_buf

  # Create instance: axis_switch_gen, and set properties
  set axis_switch_gen [ create_bd_cell -type ip -vlnv xilinx.com:ip:axis_switch:1.1 axis_switch_gen ]
  set_property -dict [ list \
   CONFIG.DECODER_REG {1} \
   CONFIG.NUM_MI {7} \
   CONFIG.NUM_SI {1} \
   CONFIG.ROUTING_MODE {1} \
 ] $axis_switch_gen

  # Create instance: axis_tproc64x32_x8_0, and set properties
  set axis_tproc64x32_x8_0 [ create_bd_cell -type ip -vlnv user.org:user:axis_tproc64x32_x8:1.0 axis_tproc64x32_x8_0 ]

  # Create instance: clk_tproc, and set properties
  set clk_tproc [ create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz:6.0 clk_tproc ]
  set_property -dict [ list \
   CONFIG.CLKOUT1_JITTER {110.870} \
   CONFIG.CLKOUT1_PHASE_ERROR {153.875} \
   CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {350} \
   CONFIG.MMCM_CLKFBOUT_MULT_F {23.625} \
   CONFIG.MMCM_CLKOUT0_DIVIDE_F {3.375} \
   CONFIG.MMCM_DIVCLK_DIVIDE {2} \
 ] $clk_tproc

  # Create instance: ps8_0_axi_periph, and set properties
  set ps8_0_axi_periph [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 ps8_0_axi_periph ]
  set_property -dict [ list \
   CONFIG.NUM_MI {14} \
 ] $ps8_0_axi_periph

  # Create instance: rst_100, and set properties
  set rst_100 [ create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_100 ]

  # Create instance: rst_adc2, and set properties
  set rst_adc2 [ create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_adc2 ]

  # Create instance: rst_dac0, and set properties
  set rst_dac0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_dac0 ]

  # Create instance: rst_dac1, and set properties
  set rst_dac1 [ create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_dac1 ]

  # Create instance: rst_dac2, and set properties
  set rst_dac2 [ create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_dac2 ]

  # Create instance: rst_dac3, and set properties
  set rst_dac3 [ create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_dac3 ]

  # Create instance: rst_tproc, and set properties
  set rst_tproc [ create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_tproc ]

  # Create instance: usp_rf_data_converter_0, and set properties
  set usp_rf_data_converter_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:usp_rf_data_converter:2.4 usp_rf_data_converter_0 ]
  set_property -dict [ list \
   CONFIG.ADC0_Enable {0} \
   CONFIG.ADC0_Fabric_Freq {0.0} \
   CONFIG.ADC2_Enable {1} \
   CONFIG.ADC2_Fabric_Freq {307.200} \
   CONFIG.ADC2_Outclk_Freq {307.200} \
   CONFIG.ADC2_PLL_Enable {true} \
   CONFIG.ADC2_Refclk_Freq {245.760} \
   CONFIG.ADC2_Sampling_Rate {2.4576} \
   CONFIG.ADC_Coarse_Mixer_Freq20 {2} \
   CONFIG.ADC_Coarse_Mixer_Freq21 {0} \
   CONFIG.ADC_Coarse_Mixer_Freq22 {0} \
   CONFIG.ADC_Coarse_Mixer_Freq23 {0} \
   CONFIG.ADC_Data_Type20 {1} \
   CONFIG.ADC_Data_Width20 {8} \
   CONFIG.ADC_Decimation_Mode00 {0} \
   CONFIG.ADC_Decimation_Mode20 {2} \
   CONFIG.ADC_Decimation_Mode21 {0} \
   CONFIG.ADC_Decimation_Mode22 {0} \
   CONFIG.ADC_Decimation_Mode23 {0} \
   CONFIG.ADC_Mixer_Mode20 {0} \
   CONFIG.ADC_Mixer_Type00 {3} \
   CONFIG.ADC_Mixer_Type20 {1} \
   CONFIG.ADC_Mixer_Type21 {3} \
   CONFIG.ADC_Mixer_Type22 {3} \
   CONFIG.ADC_Mixer_Type23 {3} \
   CONFIG.ADC_OBS01 {false} \
   CONFIG.ADC_OBS02 {false} \
   CONFIG.ADC_OBS03 {false} \
   CONFIG.ADC_OBS21 {false} \
   CONFIG.ADC_OBS22 {false} \
   CONFIG.ADC_OBS23 {false} \
   CONFIG.ADC_RESERVED_1_00 {false} \
   CONFIG.ADC_RESERVED_1_01 {false} \
   CONFIG.ADC_RESERVED_1_02 {false} \
   CONFIG.ADC_RESERVED_1_03 {false} \
   CONFIG.ADC_RESERVED_1_20 {false} \
   CONFIG.ADC_RESERVED_1_21 {false} \
   CONFIG.ADC_RESERVED_1_22 {false} \
   CONFIG.ADC_RESERVED_1_23 {false} \
   CONFIG.ADC_Slice00_Enable {false} \
   CONFIG.ADC_Slice20_Enable {true} \
   CONFIG.ADC_Slice21_Enable {false} \
   CONFIG.ADC_Slice22_Enable {false} \
   CONFIG.ADC_Slice23_Enable {false} \
   CONFIG.DAC0_Clock_Source {6} \
   CONFIG.DAC0_Enable {1} \
   CONFIG.DAC0_Fabric_Freq {430.080} \
   CONFIG.DAC0_Outclk_Freq {430.080} \
   CONFIG.DAC0_PLL_Enable {true} \
   CONFIG.DAC0_Refclk_Freq {245.760} \
   CONFIG.DAC0_Sampling_Rate {6.88128} \
   CONFIG.DAC1_Clock_Source {6} \
   CONFIG.DAC1_Enable {1} \
   CONFIG.DAC1_Fabric_Freq {430.080} \
   CONFIG.DAC1_Outclk_Freq {430.080} \
   CONFIG.DAC1_PLL_Enable {true} \
   CONFIG.DAC1_Refclk_Freq {245.760} \
   CONFIG.DAC1_Sampling_Rate {6.88128} \
   CONFIG.DAC2_Clock_Dist {1} \
   CONFIG.DAC2_Enable {1} \
   CONFIG.DAC2_Fabric_Freq {430.080} \
   CONFIG.DAC2_Outclk_Freq {430.080} \
   CONFIG.DAC2_PLL_Enable {true} \
   CONFIG.DAC2_Refclk_Freq {245.760} \
   CONFIG.DAC2_Sampling_Rate {6.88128} \
   CONFIG.DAC3_Clock_Source {6} \
   CONFIG.DAC3_Enable {1} \
   CONFIG.DAC3_Fabric_Freq {599.040} \
   CONFIG.DAC3_Outclk_Freq {599.040} \
   CONFIG.DAC3_PLL_Enable {true} \
   CONFIG.DAC3_Refclk_Freq {245.760} \
   CONFIG.DAC3_Sampling_Rate {9.58464} \
   CONFIG.DAC_Coarse_Mixer_Freq00 {3} \
   CONFIG.DAC_Coarse_Mixer_Freq10 {3} \
   CONFIG.DAC_Coarse_Mixer_Freq11 {3} \
   CONFIG.DAC_Coarse_Mixer_Freq12 {3} \
   CONFIG.DAC_Coarse_Mixer_Freq13 {3} \
   CONFIG.DAC_Coarse_Mixer_Freq20 {3} \
   CONFIG.DAC_Coarse_Mixer_Freq21 {3} \
   CONFIG.DAC_Coarse_Mixer_Freq22 {3} \
   CONFIG.DAC_Coarse_Mixer_Freq23 {3} \
   CONFIG.DAC_Coarse_Mixer_Freq30 {3} \
   CONFIG.DAC_Coarse_Mixer_Freq31 {3} \
   CONFIG.DAC_Coarse_Mixer_Freq32 {0} \
   CONFIG.DAC_Coarse_Mixer_Freq33 {0} \
   CONFIG.DAC_Data_Width00 {8} \
   CONFIG.DAC_Data_Width20 {8} \
   CONFIG.DAC_Data_Width21 {8} \
   CONFIG.DAC_Data_Width22 {8} \
   CONFIG.DAC_Data_Width23 {8} \
   CONFIG.DAC_Interpolation_Mode00 {4} \
   CONFIG.DAC_Interpolation_Mode10 {2} \
   CONFIG.DAC_Interpolation_Mode11 {2} \
   CONFIG.DAC_Interpolation_Mode12 {2} \
   CONFIG.DAC_Interpolation_Mode13 {2} \
   CONFIG.DAC_Interpolation_Mode20 {4} \
   CONFIG.DAC_Interpolation_Mode21 {4} \
   CONFIG.DAC_Interpolation_Mode22 {4} \
   CONFIG.DAC_Interpolation_Mode23 {4} \
   CONFIG.DAC_Interpolation_Mode30 {1} \
   CONFIG.DAC_Interpolation_Mode31 {1} \
   CONFIG.DAC_Interpolation_Mode32 {0} \
   CONFIG.DAC_Interpolation_Mode33 {0} \
   CONFIG.DAC_Mixer_Mode00 {0} \
   CONFIG.DAC_Mixer_Mode10 {0} \
   CONFIG.DAC_Mixer_Mode11 {0} \
   CONFIG.DAC_Mixer_Mode12 {0} \
   CONFIG.DAC_Mixer_Mode13 {0} \
   CONFIG.DAC_Mixer_Mode20 {0} \
   CONFIG.DAC_Mixer_Mode21 {0} \
   CONFIG.DAC_Mixer_Mode22 {0} \
   CONFIG.DAC_Mixer_Mode23 {0} \
   CONFIG.DAC_Mixer_Type00 {2} \
   CONFIG.DAC_Mixer_Type10 {2} \
   CONFIG.DAC_Mixer_Type11 {2} \
   CONFIG.DAC_Mixer_Type12 {2} \
   CONFIG.DAC_Mixer_Type13 {2} \
   CONFIG.DAC_Mixer_Type20 {2} \
   CONFIG.DAC_Mixer_Type21 {2} \
   CONFIG.DAC_Mixer_Type22 {2} \
   CONFIG.DAC_Mixer_Type23 {2} \
   CONFIG.DAC_Mixer_Type30 {1} \
   CONFIG.DAC_Mixer_Type31 {1} \
   CONFIG.DAC_Mixer_Type32 {3} \
   CONFIG.DAC_Mixer_Type33 {3} \
   CONFIG.DAC_Mode20 {0} \
   CONFIG.DAC_Mode21 {0} \
   CONFIG.DAC_Mode30 {3} \
   CONFIG.DAC_Mode31 {3} \
   CONFIG.DAC_Mode32 {0} \
   CONFIG.DAC_Mode33 {0} \
   CONFIG.DAC_NCO_Freq00 {0.5} \
   CONFIG.DAC_NCO_Freq10 {1.0} \
   CONFIG.DAC_NCO_Freq11 {1.0} \
   CONFIG.DAC_NCO_Freq12 {1.0} \
   CONFIG.DAC_NCO_Freq13 {1.0} \
   CONFIG.DAC_NCO_Freq20 {0.5} \
   CONFIG.DAC_NCO_Freq21 {0.5} \
   CONFIG.DAC_NCO_Freq22 {0.5} \
   CONFIG.DAC_NCO_Freq23 {0.5} \
   CONFIG.DAC_RESERVED_1_00 {false} \
   CONFIG.DAC_RESERVED_1_01 {false} \
   CONFIG.DAC_RESERVED_1_02 {false} \
   CONFIG.DAC_RESERVED_1_03 {false} \
   CONFIG.DAC_RESERVED_1_10 {false} \
   CONFIG.DAC_RESERVED_1_11 {false} \
   CONFIG.DAC_RESERVED_1_12 {false} \
   CONFIG.DAC_RESERVED_1_13 {false} \
   CONFIG.DAC_RESERVED_1_20 {false} \
   CONFIG.DAC_RESERVED_1_21 {false} \
   CONFIG.DAC_RESERVED_1_22 {false} \
   CONFIG.DAC_RESERVED_1_23 {false} \
   CONFIG.DAC_RESERVED_1_30 {false} \
   CONFIG.DAC_RESERVED_1_31 {false} \
   CONFIG.DAC_RESERVED_1_32 {false} \
   CONFIG.DAC_RESERVED_1_33 {false} \
   CONFIG.DAC_Slice00_Enable {true} \
   CONFIG.DAC_Slice10_Enable {true} \
   CONFIG.DAC_Slice11_Enable {true} \
   CONFIG.DAC_Slice12_Enable {true} \
   CONFIG.DAC_Slice13_Enable {true} \
   CONFIG.DAC_Slice20_Enable {true} \
   CONFIG.DAC_Slice21_Enable {true} \
   CONFIG.DAC_Slice22_Enable {true} \
   CONFIG.DAC_Slice23_Enable {true} \
   CONFIG.DAC_Slice30_Enable {true} \
   CONFIG.DAC_Slice31_Enable {true} \
   CONFIG.DAC_Slice32_Enable {false} \
   CONFIG.DAC_Slice33_Enable {false} \
 ] $usp_rf_data_converter_0

  # Create instance: vect2bits_9_0, and set properties
  set block_name vect2bits_9
  set block_cell_name vect2bits_9_0
  if { [catch {set vect2bits_9_0 [create_bd_cell -type module -reference $block_name $block_cell_name] } errmsg] } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2095 -severity "ERROR" "Unable to add referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   } elseif { $vect2bits_9_0 eq "" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2096 -severity "ERROR" "Unable to referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   }
  
  # Create instance: xlconstant_0, and set properties
  set xlconstant_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 xlconstant_0 ]
  set_property -dict [ list \
   CONFIG.CONST_VAL {0} \
   CONFIG.CONST_WIDTH {64} \
 ] $xlconstant_0

  # Create instance: xlconstant_1, and set properties
  set xlconstant_1 [ create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 xlconstant_1 ]
  set_property -dict [ list \
   CONFIG.CONST_VAL {1} \
   CONFIG.CONST_WIDTH {1} \
 ] $xlconstant_1

  # Create instance: xlconstant_2, and set properties
  set xlconstant_2 [ create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 xlconstant_2 ]
  set_property -dict [ list \
   CONFIG.CONST_VAL {0} \
   CONFIG.CONST_WIDTH {1} \
 ] $xlconstant_2

  # Create instance: xlconstant_3, and set properties
  set xlconstant_3 [ create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 xlconstant_3 ]
  set_property -dict [ list \
   CONFIG.CONST_VAL {0} \
   CONFIG.CONST_WIDTH {8} \
 ] $xlconstant_3

  # Create instance: zynq_ultra_ps_e_0, and set properties
  set zynq_ultra_ps_e_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e:3.3 zynq_ultra_ps_e_0 ]
  set_property -dict [ list \
   CONFIG.PSU_BANK_0_IO_STANDARD {LVCMOS18} \
   CONFIG.PSU_BANK_1_IO_STANDARD {LVCMOS18} \
   CONFIG.PSU_BANK_2_IO_STANDARD {LVCMOS18} \
   CONFIG.PSU_DDR_RAM_HIGHADDR {0xFFFFFFFF} \
   CONFIG.PSU_DDR_RAM_HIGHADDR_OFFSET {0x800000000} \
   CONFIG.PSU_DDR_RAM_LOWADDR_OFFSET {0x80000000} \
   CONFIG.PSU_DYNAMIC_DDR_CONFIG_EN {1} \
   CONFIG.PSU_MIO_0_DIRECTION {out} \
   CONFIG.PSU_MIO_0_INPUT_TYPE {cmos} \
   CONFIG.PSU_MIO_0_POLARITY {Default} \
   CONFIG.PSU_MIO_10_DIRECTION {inout} \
   CONFIG.PSU_MIO_10_POLARITY {Default} \
   CONFIG.PSU_MIO_11_DIRECTION {inout} \
   CONFIG.PSU_MIO_11_POLARITY {Default} \
   CONFIG.PSU_MIO_12_DIRECTION {out} \
   CONFIG.PSU_MIO_12_INPUT_TYPE {cmos} \
   CONFIG.PSU_MIO_12_POLARITY {Default} \
   CONFIG.PSU_MIO_13_DIRECTION {inout} \
   CONFIG.PSU_MIO_13_POLARITY {Default} \
   CONFIG.PSU_MIO_14_DIRECTION {inout} \
   CONFIG.PSU_MIO_14_POLARITY {Default} \
   CONFIG.PSU_MIO_15_DIRECTION {inout} \
   CONFIG.PSU_MIO_15_POLARITY {Default} \
   CONFIG.PSU_MIO_16_DIRECTION {inout} \
   CONFIG.PSU_MIO_16_POLARITY {Default} \
   CONFIG.PSU_MIO_17_DIRECTION {inout} \
   CONFIG.PSU_MIO_17_POLARITY {Default} \
   CONFIG.PSU_MIO_18_DIRECTION {in} \
   CONFIG.PSU_MIO_18_DRIVE_STRENGTH {12} \
   CONFIG.PSU_MIO_18_POLARITY {Default} \
   CONFIG.PSU_MIO_18_SLEW {fast} \
   CONFIG.PSU_MIO_19_DIRECTION {out} \
   CONFIG.PSU_MIO_19_INPUT_TYPE {cmos} \
   CONFIG.PSU_MIO_19_POLARITY {Default} \
   CONFIG.PSU_MIO_1_DIRECTION {inout} \
   CONFIG.PSU_MIO_1_POLARITY {Default} \
   CONFIG.PSU_MIO_20_DIRECTION {inout} \
   CONFIG.PSU_MIO_20_POLARITY {Default} \
   CONFIG.PSU_MIO_21_DIRECTION {inout} \
   CONFIG.PSU_MIO_21_POLARITY {Default} \
   CONFIG.PSU_MIO_22_DIRECTION {inout} \
   CONFIG.PSU_MIO_22_POLARITY {Default} \
   CONFIG.PSU_MIO_23_DIRECTION {inout} \
   CONFIG.PSU_MIO_23_POLARITY {Default} \
   CONFIG.PSU_MIO_24_DIRECTION {inout} \
   CONFIG.PSU_MIO_24_POLARITY {Default} \
   CONFIG.PSU_MIO_25_DIRECTION {inout} \
   CONFIG.PSU_MIO_25_POLARITY {Default} \
   CONFIG.PSU_MIO_26_DIRECTION {inout} \
   CONFIG.PSU_MIO_26_POLARITY {Default} \
   CONFIG.PSU_MIO_27_DIRECTION {inout} \
   CONFIG.PSU_MIO_27_POLARITY {Default} \
   CONFIG.PSU_MIO_28_DIRECTION {inout} \
   CONFIG.PSU_MIO_28_POLARITY {Default} \
   CONFIG.PSU_MIO_29_DIRECTION {inout} \
   CONFIG.PSU_MIO_29_POLARITY {Default} \
   CONFIG.PSU_MIO_2_DIRECTION {inout} \
   CONFIG.PSU_MIO_2_POLARITY {Default} \
   CONFIG.PSU_MIO_30_DIRECTION {inout} \
   CONFIG.PSU_MIO_30_POLARITY {Default} \
   CONFIG.PSU_MIO_31_DIRECTION {inout} \
   CONFIG.PSU_MIO_31_POLARITY {Default} \
   CONFIG.PSU_MIO_32_DIRECTION {out} \
   CONFIG.PSU_MIO_32_INPUT_TYPE {cmos} \
   CONFIG.PSU_MIO_32_POLARITY {Default} \
   CONFIG.PSU_MIO_33_DIRECTION {out} \
   CONFIG.PSU_MIO_33_INPUT_TYPE {cmos} \
   CONFIG.PSU_MIO_33_POLARITY {Default} \
   CONFIG.PSU_MIO_34_DIRECTION {out} \
   CONFIG.PSU_MIO_34_INPUT_TYPE {cmos} \
   CONFIG.PSU_MIO_34_POLARITY {Default} \
   CONFIG.PSU_MIO_35_DIRECTION {out} \
   CONFIG.PSU_MIO_35_INPUT_TYPE {cmos} \
   CONFIG.PSU_MIO_35_POLARITY {Default} \
   CONFIG.PSU_MIO_36_DIRECTION {out} \
   CONFIG.PSU_MIO_36_INPUT_TYPE {cmos} \
   CONFIG.PSU_MIO_36_POLARITY {Default} \
   CONFIG.PSU_MIO_37_DIRECTION {out} \
   CONFIG.PSU_MIO_37_INPUT_TYPE {cmos} \
   CONFIG.PSU_MIO_37_POLARITY {Default} \
   CONFIG.PSU_MIO_38_DIRECTION {inout} \
   CONFIG.PSU_MIO_38_POLARITY {Default} \
   CONFIG.PSU_MIO_39_DIRECTION {inout} \
   CONFIG.PSU_MIO_39_POLARITY {Default} \
   CONFIG.PSU_MIO_3_DIRECTION {inout} \
   CONFIG.PSU_MIO_3_POLARITY {Default} \
   CONFIG.PSU_MIO_40_DIRECTION {inout} \
   CONFIG.PSU_MIO_40_POLARITY {Default} \
   CONFIG.PSU_MIO_41_DIRECTION {inout} \
   CONFIG.PSU_MIO_41_POLARITY {Default} \
   CONFIG.PSU_MIO_42_DIRECTION {inout} \
   CONFIG.PSU_MIO_42_POLARITY {Default} \
   CONFIG.PSU_MIO_43_DIRECTION {inout} \
   CONFIG.PSU_MIO_43_POLARITY {Default} \
   CONFIG.PSU_MIO_44_DIRECTION {inout} \
   CONFIG.PSU_MIO_44_POLARITY {Default} \
   CONFIG.PSU_MIO_45_DIRECTION {in} \
   CONFIG.PSU_MIO_45_DRIVE_STRENGTH {12} \
   CONFIG.PSU_MIO_45_POLARITY {Default} \
   CONFIG.PSU_MIO_45_SLEW {fast} \
   CONFIG.PSU_MIO_46_DIRECTION {inout} \
   CONFIG.PSU_MIO_46_POLARITY {Default} \
   CONFIG.PSU_MIO_47_DIRECTION {inout} \
   CONFIG.PSU_MIO_47_POLARITY {Default} \
   CONFIG.PSU_MIO_48_DIRECTION {inout} \
   CONFIG.PSU_MIO_48_POLARITY {Default} \
   CONFIG.PSU_MIO_49_DIRECTION {inout} \
   CONFIG.PSU_MIO_49_POLARITY {Default} \
   CONFIG.PSU_MIO_4_DIRECTION {inout} \
   CONFIG.PSU_MIO_4_POLARITY {Default} \
   CONFIG.PSU_MIO_50_DIRECTION {inout} \
   CONFIG.PSU_MIO_50_POLARITY {Default} \
   CONFIG.PSU_MIO_51_DIRECTION {out} \
   CONFIG.PSU_MIO_51_INPUT_TYPE {cmos} \
   CONFIG.PSU_MIO_51_POLARITY {Default} \
   CONFIG.PSU_MIO_52_DIRECTION {in} \
   CONFIG.PSU_MIO_52_DRIVE_STRENGTH {12} \
   CONFIG.PSU_MIO_52_POLARITY {Default} \
   CONFIG.PSU_MIO_52_SLEW {fast} \
   CONFIG.PSU_MIO_53_DIRECTION {in} \
   CONFIG.PSU_MIO_53_DRIVE_STRENGTH {12} \
   CONFIG.PSU_MIO_53_POLARITY {Default} \
   CONFIG.PSU_MIO_53_SLEW {fast} \
   CONFIG.PSU_MIO_54_DIRECTION {inout} \
   CONFIG.PSU_MIO_54_POLARITY {Default} \
   CONFIG.PSU_MIO_55_DIRECTION {in} \
   CONFIG.PSU_MIO_55_DRIVE_STRENGTH {12} \
   CONFIG.PSU_MIO_55_POLARITY {Default} \
   CONFIG.PSU_MIO_55_SLEW {fast} \
   CONFIG.PSU_MIO_56_DIRECTION {inout} \
   CONFIG.PSU_MIO_56_POLARITY {Default} \
   CONFIG.PSU_MIO_57_DIRECTION {inout} \
   CONFIG.PSU_MIO_57_POLARITY {Default} \
   CONFIG.PSU_MIO_58_DIRECTION {out} \
   CONFIG.PSU_MIO_58_INPUT_TYPE {cmos} \
   CONFIG.PSU_MIO_58_POLARITY {Default} \
   CONFIG.PSU_MIO_59_DIRECTION {inout} \
   CONFIG.PSU_MIO_59_POLARITY {Default} \
   CONFIG.PSU_MIO_5_DIRECTION {out} \
   CONFIG.PSU_MIO_5_INPUT_TYPE {cmos} \
   CONFIG.PSU_MIO_5_POLARITY {Default} \
   CONFIG.PSU_MIO_60_DIRECTION {inout} \
   CONFIG.PSU_MIO_60_POLARITY {Default} \
   CONFIG.PSU_MIO_61_DIRECTION {inout} \
   CONFIG.PSU_MIO_61_POLARITY {Default} \
   CONFIG.PSU_MIO_62_DIRECTION {inout} \
   CONFIG.PSU_MIO_62_POLARITY {Default} \
   CONFIG.PSU_MIO_63_DIRECTION {inout} \
   CONFIG.PSU_MIO_63_POLARITY {Default} \
   CONFIG.PSU_MIO_64_DIRECTION {out} \
   CONFIG.PSU_MIO_64_INPUT_TYPE {cmos} \
   CONFIG.PSU_MIO_64_POLARITY {Default} \
   CONFIG.PSU_MIO_65_DIRECTION {out} \
   CONFIG.PSU_MIO_65_INPUT_TYPE {cmos} \
   CONFIG.PSU_MIO_65_POLARITY {Default} \
   CONFIG.PSU_MIO_66_DIRECTION {out} \
   CONFIG.PSU_MIO_66_INPUT_TYPE {cmos} \
   CONFIG.PSU_MIO_66_POLARITY {Default} \
   CONFIG.PSU_MIO_67_DIRECTION {out} \
   CONFIG.PSU_MIO_67_INPUT_TYPE {cmos} \
   CONFIG.PSU_MIO_67_POLARITY {Default} \
   CONFIG.PSU_MIO_68_DIRECTION {out} \
   CONFIG.PSU_MIO_68_INPUT_TYPE {cmos} \
   CONFIG.PSU_MIO_68_POLARITY {Default} \
   CONFIG.PSU_MIO_69_DIRECTION {out} \
   CONFIG.PSU_MIO_69_INPUT_TYPE {cmos} \
   CONFIG.PSU_MIO_69_POLARITY {Default} \
   CONFIG.PSU_MIO_6_DIRECTION {out} \
   CONFIG.PSU_MIO_6_INPUT_TYPE {cmos} \
   CONFIG.PSU_MIO_6_POLARITY {Default} \
   CONFIG.PSU_MIO_70_DIRECTION {in} \
   CONFIG.PSU_MIO_70_DRIVE_STRENGTH {12} \
   CONFIG.PSU_MIO_70_POLARITY {Default} \
   CONFIG.PSU_MIO_70_SLEW {fast} \
   CONFIG.PSU_MIO_71_DIRECTION {in} \
   CONFIG.PSU_MIO_71_DRIVE_STRENGTH {12} \
   CONFIG.PSU_MIO_71_POLARITY {Default} \
   CONFIG.PSU_MIO_71_SLEW {fast} \
   CONFIG.PSU_MIO_72_DIRECTION {in} \
   CONFIG.PSU_MIO_72_DRIVE_STRENGTH {12} \
   CONFIG.PSU_MIO_72_POLARITY {Default} \
   CONFIG.PSU_MIO_72_SLEW {fast} \
   CONFIG.PSU_MIO_73_DIRECTION {in} \
   CONFIG.PSU_MIO_73_DRIVE_STRENGTH {12} \
   CONFIG.PSU_MIO_73_POLARITY {Default} \
   CONFIG.PSU_MIO_73_SLEW {fast} \
   CONFIG.PSU_MIO_74_DIRECTION {in} \
   CONFIG.PSU_MIO_74_DRIVE_STRENGTH {12} \
   CONFIG.PSU_MIO_74_POLARITY {Default} \
   CONFIG.PSU_MIO_74_SLEW {fast} \
   CONFIG.PSU_MIO_75_DIRECTION {in} \
   CONFIG.PSU_MIO_75_DRIVE_STRENGTH {12} \
   CONFIG.PSU_MIO_75_POLARITY {Default} \
   CONFIG.PSU_MIO_75_SLEW {fast} \
   CONFIG.PSU_MIO_76_DIRECTION {out} \
   CONFIG.PSU_MIO_76_INPUT_TYPE {cmos} \
   CONFIG.PSU_MIO_76_POLARITY {Default} \
   CONFIG.PSU_MIO_77_DIRECTION {inout} \
   CONFIG.PSU_MIO_77_POLARITY {Default} \
   CONFIG.PSU_MIO_7_DIRECTION {out} \
   CONFIG.PSU_MIO_7_INPUT_TYPE {cmos} \
   CONFIG.PSU_MIO_7_POLARITY {Default} \
   CONFIG.PSU_MIO_8_DIRECTION {inout} \
   CONFIG.PSU_MIO_8_POLARITY {Default} \
   CONFIG.PSU_MIO_9_DIRECTION {inout} \
   CONFIG.PSU_MIO_9_POLARITY {Default} \
   CONFIG.PSU_MIO_TREE_PERIPHERALS {Quad SPI Flash#Quad SPI Flash#Quad SPI Flash#Quad SPI Flash#Quad SPI Flash#Quad SPI Flash#Feedback Clk#Quad SPI Flash#Quad SPI Flash#Quad SPI Flash#Quad SPI Flash#Quad SPI Flash#Quad SPI Flash#GPIO0 MIO#I2C 0#I2C 0#I2C 1#I2C 1#UART 0#UART 0#GPIO0 MIO#GPIO0 MIO#GPIO0 MIO#GPIO0 MIO#GPIO0 MIO#GPIO0 MIO#GPIO1 MIO#GPIO1 MIO#GPIO1 MIO#GPIO1 MIO#GPIO1 MIO#GPIO1 MIO#PMU GPO 0#PMU GPO 1#PMU GPO 2#PMU GPO 3#PMU GPO 4#PMU GPO 5#GPIO1 MIO#SD 1#SD 1#SD 1#SD 1#GPIO1 MIO#GPIO1 MIO#SD 1#SD 1#SD 1#SD 1#SD 1#SD 1#SD 1#USB 0#USB 0#USB 0#USB 0#USB 0#USB 0#USB 0#USB 0#USB 0#USB 0#USB 0#USB 0#Gem 3#Gem 3#Gem 3#Gem 3#Gem 3#Gem 3#Gem 3#Gem 3#Gem 3#Gem 3#Gem 3#Gem 3#MDIO 3#MDIO 3} \
   CONFIG.PSU_MIO_TREE_SIGNALS {sclk_out#miso_mo1#mo2#mo3#mosi_mi0#n_ss_out#clk_for_lpbk#n_ss_out_upper#mo_upper[0]#mo_upper[1]#mo_upper[2]#mo_upper[3]#sclk_out_upper#gpio0[13]#scl_out#sda_out#scl_out#sda_out#rxd#txd#gpio0[20]#gpio0[21]#gpio0[22]#gpio0[23]#gpio0[24]#gpio0[25]#gpio1[26]#gpio1[27]#gpio1[28]#gpio1[29]#gpio1[30]#gpio1[31]#gpo[0]#gpo[1]#gpo[2]#gpo[3]#gpo[4]#gpo[5]#gpio1[38]#sdio1_data_out[4]#sdio1_data_out[5]#sdio1_data_out[6]#sdio1_data_out[7]#gpio1[43]#gpio1[44]#sdio1_cd_n#sdio1_data_out[0]#sdio1_data_out[1]#sdio1_data_out[2]#sdio1_data_out[3]#sdio1_cmd_out#sdio1_clk_out#ulpi_clk_in#ulpi_dir#ulpi_tx_data[2]#ulpi_nxt#ulpi_tx_data[0]#ulpi_tx_data[1]#ulpi_stp#ulpi_tx_data[3]#ulpi_tx_data[4]#ulpi_tx_data[5]#ulpi_tx_data[6]#ulpi_tx_data[7]#rgmii_tx_clk#rgmii_txd[0]#rgmii_txd[1]#rgmii_txd[2]#rgmii_txd[3]#rgmii_tx_ctl#rgmii_rx_clk#rgmii_rxd[0]#rgmii_rxd[1]#rgmii_rxd[2]#rgmii_rxd[3]#rgmii_rx_ctl#gem3_mdc#gem3_mdio_out} \
   CONFIG.PSU_SD1_INTERNAL_BUS_WIDTH {8} \
   CONFIG.PSU_USB3__DUAL_CLOCK_ENABLE {1} \
   CONFIG.PSU__ACT_DDR_FREQ_MHZ {1049.989502} \
   CONFIG.PSU__AFI0_COHERENCY {0} \
   CONFIG.PSU__AFI1_COHERENCY {0} \
   CONFIG.PSU__CAN1__GRP_CLK__ENABLE {0} \
   CONFIG.PSU__CAN1__PERIPHERAL__ENABLE {0} \
   CONFIG.PSU__CRF_APB__ACPU_CTRL__ACT_FREQMHZ {1199.988037} \
   CONFIG.PSU__CRF_APB__ACPU_CTRL__DIVISOR0 {1} \
   CONFIG.PSU__CRF_APB__ACPU_CTRL__FREQMHZ {1200} \
   CONFIG.PSU__CRF_APB__ACPU_CTRL__SRCSEL {APLL} \
   CONFIG.PSU__CRF_APB__APLL_CTRL__DIV2 {1} \
   CONFIG.PSU__CRF_APB__APLL_CTRL__FBDIV {72} \
   CONFIG.PSU__CRF_APB__APLL_CTRL__FRACDATA {0.000000} \
   CONFIG.PSU__CRF_APB__APLL_CTRL__SRCSEL {PSS_REF_CLK} \
   CONFIG.PSU__CRF_APB__APLL_FRAC_CFG__ENABLED {0} \
   CONFIG.PSU__CRF_APB__APLL_TO_LPD_CTRL__DIVISOR0 {3} \
   CONFIG.PSU__CRF_APB__DBG_FPD_CTRL__ACT_FREQMHZ {249.997498} \
   CONFIG.PSU__CRF_APB__DBG_FPD_CTRL__DIVISOR0 {2} \
   CONFIG.PSU__CRF_APB__DBG_FPD_CTRL__FREQMHZ {250} \
   CONFIG.PSU__CRF_APB__DBG_FPD_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRF_APB__DBG_TRACE_CTRL__DIVISOR0 {5} \
   CONFIG.PSU__CRF_APB__DBG_TRACE_CTRL__FREQMHZ {250} \
   CONFIG.PSU__CRF_APB__DBG_TRACE_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRF_APB__DBG_TSTMP_CTRL__ACT_FREQMHZ {249.997498} \
   CONFIG.PSU__CRF_APB__DBG_TSTMP_CTRL__DIVISOR0 {2} \
   CONFIG.PSU__CRF_APB__DBG_TSTMP_CTRL__FREQMHZ {250} \
   CONFIG.PSU__CRF_APB__DBG_TSTMP_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRF_APB__DDR_CTRL__ACT_FREQMHZ {524.994751} \
   CONFIG.PSU__CRF_APB__DDR_CTRL__DIVISOR0 {2} \
   CONFIG.PSU__CRF_APB__DDR_CTRL__FREQMHZ {1066} \
   CONFIG.PSU__CRF_APB__DDR_CTRL__SRCSEL {DPLL} \
   CONFIG.PSU__CRF_APB__DPDMA_REF_CTRL__ACT_FREQMHZ {599.994019} \
   CONFIG.PSU__CRF_APB__DPDMA_REF_CTRL__DIVISOR0 {2} \
   CONFIG.PSU__CRF_APB__DPDMA_REF_CTRL__FREQMHZ {600} \
   CONFIG.PSU__CRF_APB__DPDMA_REF_CTRL__SRCSEL {APLL} \
   CONFIG.PSU__CRF_APB__DPLL_CTRL__DIV2 {1} \
   CONFIG.PSU__CRF_APB__DPLL_CTRL__FBDIV {63} \
   CONFIG.PSU__CRF_APB__DPLL_CTRL__FRACDATA {0.000000} \
   CONFIG.PSU__CRF_APB__DPLL_CTRL__SRCSEL {PSS_REF_CLK} \
   CONFIG.PSU__CRF_APB__DPLL_FRAC_CFG__ENABLED {0} \
   CONFIG.PSU__CRF_APB__DPLL_TO_LPD_CTRL__DIVISOR0 {2} \
   CONFIG.PSU__CRF_APB__DP_AUDIO_REF_CTRL__DIVISOR0 {63} \
   CONFIG.PSU__CRF_APB__DP_AUDIO_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRF_APB__DP_AUDIO_REF_CTRL__SRCSEL {RPLL} \
   CONFIG.PSU__CRF_APB__DP_STC_REF_CTRL__DIVISOR0 {6} \
   CONFIG.PSU__CRF_APB__DP_STC_REF_CTRL__DIVISOR1 {10} \
   CONFIG.PSU__CRF_APB__DP_STC_REF_CTRL__SRCSEL {RPLL} \
   CONFIG.PSU__CRF_APB__DP_VIDEO_REF_CTRL__DIVISOR0 {5} \
   CONFIG.PSU__CRF_APB__DP_VIDEO_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRF_APB__DP_VIDEO_REF_CTRL__SRCSEL {VPLL} \
   CONFIG.PSU__CRF_APB__GDMA_REF_CTRL__ACT_FREQMHZ {599.994019} \
   CONFIG.PSU__CRF_APB__GDMA_REF_CTRL__DIVISOR0 {2} \
   CONFIG.PSU__CRF_APB__GDMA_REF_CTRL__FREQMHZ {600} \
   CONFIG.PSU__CRF_APB__GDMA_REF_CTRL__SRCSEL {APLL} \
   CONFIG.PSU__CRF_APB__GPU_REF_CTRL__DIVISOR0 {3} \
   CONFIG.PSU__CRF_APB__GPU_REF_CTRL__FREQMHZ {500} \
   CONFIG.PSU__CRF_APB__GPU_REF_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRF_APB__PCIE_REF_CTRL__DIVISOR0 {6} \
   CONFIG.PSU__CRF_APB__PCIE_REF_CTRL__FREQMHZ {250} \
   CONFIG.PSU__CRF_APB__PCIE_REF_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRF_APB__SATA_REF_CTRL__ACT_FREQMHZ {249.997498} \
   CONFIG.PSU__CRF_APB__SATA_REF_CTRL__DIVISOR0 {2} \
   CONFIG.PSU__CRF_APB__SATA_REF_CTRL__FREQMHZ {250} \
   CONFIG.PSU__CRF_APB__SATA_REF_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRF_APB__TOPSW_LSBUS_CTRL__ACT_FREQMHZ {99.999001} \
   CONFIG.PSU__CRF_APB__TOPSW_LSBUS_CTRL__DIVISOR0 {5} \
   CONFIG.PSU__CRF_APB__TOPSW_LSBUS_CTRL__FREQMHZ {100} \
   CONFIG.PSU__CRF_APB__TOPSW_LSBUS_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRF_APB__TOPSW_MAIN_CTRL__ACT_FREQMHZ {524.994751} \
   CONFIG.PSU__CRF_APB__TOPSW_MAIN_CTRL__DIVISOR0 {2} \
   CONFIG.PSU__CRF_APB__TOPSW_MAIN_CTRL__FREQMHZ {533.33} \
   CONFIG.PSU__CRF_APB__TOPSW_MAIN_CTRL__SRCSEL {DPLL} \
   CONFIG.PSU__CRF_APB__VPLL_CTRL__DIV2 {1} \
   CONFIG.PSU__CRF_APB__VPLL_CTRL__FBDIV {90} \
   CONFIG.PSU__CRF_APB__VPLL_CTRL__FRACDATA {0.000000} \
   CONFIG.PSU__CRF_APB__VPLL_CTRL__SRCSEL {PSS_REF_CLK} \
   CONFIG.PSU__CRF_APB__VPLL_FRAC_CFG__ENABLED {0} \
   CONFIG.PSU__CRF_APB__VPLL_TO_LPD_CTRL__DIVISOR0 {3} \
   CONFIG.PSU__CRL_APB__ADMA_REF_CTRL__ACT_FREQMHZ {499.994995} \
   CONFIG.PSU__CRL_APB__ADMA_REF_CTRL__DIVISOR0 {3} \
   CONFIG.PSU__CRL_APB__ADMA_REF_CTRL__FREQMHZ {500} \
   CONFIG.PSU__CRL_APB__ADMA_REF_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRL_APB__AFI6_REF_CTRL__DIVISOR0 {3} \
   CONFIG.PSU__CRL_APB__AMS_REF_CTRL__ACT_FREQMHZ {49.999500} \
   CONFIG.PSU__CRL_APB__AMS_REF_CTRL__DIVISOR0 {30} \
   CONFIG.PSU__CRL_APB__AMS_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__CAN0_REF_CTRL__DIVISOR0 {15} \
   CONFIG.PSU__CRL_APB__CAN0_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__CAN1_REF_CTRL__DIVISOR0 {15} \
   CONFIG.PSU__CRL_APB__CAN1_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__CAN1_REF_CTRL__FREQMHZ {100} \
   CONFIG.PSU__CRL_APB__CAN1_REF_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRL_APB__CPU_R5_CTRL__ACT_FREQMHZ {499.994995} \
   CONFIG.PSU__CRL_APB__CPU_R5_CTRL__DIVISOR0 {3} \
   CONFIG.PSU__CRL_APB__CPU_R5_CTRL__FREQMHZ {500} \
   CONFIG.PSU__CRL_APB__CPU_R5_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRL_APB__DBG_LPD_CTRL__ACT_FREQMHZ {249.997498} \
   CONFIG.PSU__CRL_APB__DBG_LPD_CTRL__DIVISOR0 {6} \
   CONFIG.PSU__CRL_APB__DBG_LPD_CTRL__FREQMHZ {250} \
   CONFIG.PSU__CRL_APB__DBG_LPD_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRL_APB__DLL_REF_CTRL__ACT_FREQMHZ {1499.984985} \
   CONFIG.PSU__CRL_APB__GEM0_REF_CTRL__DIVISOR0 {12} \
   CONFIG.PSU__CRL_APB__GEM0_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__GEM1_REF_CTRL__DIVISOR0 {12} \
   CONFIG.PSU__CRL_APB__GEM1_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__GEM2_REF_CTRL__DIVISOR0 {12} \
   CONFIG.PSU__CRL_APB__GEM2_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__GEM3_REF_CTRL__ACT_FREQMHZ {124.998749} \
   CONFIG.PSU__CRL_APB__GEM3_REF_CTRL__DIVISOR0 {12} \
   CONFIG.PSU__CRL_APB__GEM3_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__GEM3_REF_CTRL__FREQMHZ {125} \
   CONFIG.PSU__CRL_APB__GEM3_REF_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRL_APB__GEM_TSU_REF_CTRL__ACT_FREQMHZ {249.997498} \
   CONFIG.PSU__CRL_APB__GEM_TSU_REF_CTRL__DIVISOR0 {6} \
   CONFIG.PSU__CRL_APB__GEM_TSU_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__GEM_TSU_REF_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRL_APB__I2C0_REF_CTRL__ACT_FREQMHZ {99.999001} \
   CONFIG.PSU__CRL_APB__I2C0_REF_CTRL__DIVISOR0 {15} \
   CONFIG.PSU__CRL_APB__I2C0_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__I2C0_REF_CTRL__FREQMHZ {100} \
   CONFIG.PSU__CRL_APB__I2C0_REF_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRL_APB__I2C1_REF_CTRL__ACT_FREQMHZ {99.999001} \
   CONFIG.PSU__CRL_APB__I2C1_REF_CTRL__DIVISOR0 {15} \
   CONFIG.PSU__CRL_APB__I2C1_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__I2C1_REF_CTRL__FREQMHZ {100} \
   CONFIG.PSU__CRL_APB__I2C1_REF_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRL_APB__IOPLL_CTRL__DIV2 {1} \
   CONFIG.PSU__CRL_APB__IOPLL_CTRL__FBDIV {90} \
   CONFIG.PSU__CRL_APB__IOPLL_CTRL__FRACDATA {0.000000} \
   CONFIG.PSU__CRL_APB__IOPLL_CTRL__SRCSEL {PSS_REF_CLK} \
   CONFIG.PSU__CRL_APB__IOPLL_FRAC_CFG__ENABLED {0} \
   CONFIG.PSU__CRL_APB__IOPLL_TO_FPD_CTRL__DIVISOR0 {3} \
   CONFIG.PSU__CRL_APB__IOU_SWITCH_CTRL__ACT_FREQMHZ {249.997498} \
   CONFIG.PSU__CRL_APB__IOU_SWITCH_CTRL__DIVISOR0 {6} \
   CONFIG.PSU__CRL_APB__IOU_SWITCH_CTRL__FREQMHZ {250} \
   CONFIG.PSU__CRL_APB__IOU_SWITCH_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRL_APB__LPD_LSBUS_CTRL__ACT_FREQMHZ {99.999001} \
   CONFIG.PSU__CRL_APB__LPD_LSBUS_CTRL__DIVISOR0 {15} \
   CONFIG.PSU__CRL_APB__LPD_LSBUS_CTRL__FREQMHZ {100} \
   CONFIG.PSU__CRL_APB__LPD_LSBUS_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRL_APB__LPD_SWITCH_CTRL__ACT_FREQMHZ {499.994995} \
   CONFIG.PSU__CRL_APB__LPD_SWITCH_CTRL__DIVISOR0 {3} \
   CONFIG.PSU__CRL_APB__LPD_SWITCH_CTRL__FREQMHZ {500} \
   CONFIG.PSU__CRL_APB__LPD_SWITCH_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRL_APB__NAND_REF_CTRL__DIVISOR0 {15} \
   CONFIG.PSU__CRL_APB__NAND_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__PCAP_CTRL__ACT_FREQMHZ {187.498123} \
   CONFIG.PSU__CRL_APB__PCAP_CTRL__DIVISOR0 {8} \
   CONFIG.PSU__CRL_APB__PCAP_CTRL__FREQMHZ {200} \
   CONFIG.PSU__CRL_APB__PCAP_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRL_APB__PL0_REF_CTRL__ACT_FREQMHZ {99.999001} \
   CONFIG.PSU__CRL_APB__PL0_REF_CTRL__DIVISOR0 {15} \
   CONFIG.PSU__CRL_APB__PL0_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ {100} \
   CONFIG.PSU__CRL_APB__PL0_REF_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRL_APB__PL1_REF_CTRL__DIVISOR0 {4} \
   CONFIG.PSU__CRL_APB__PL1_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__PL2_REF_CTRL__DIVISOR0 {4} \
   CONFIG.PSU__CRL_APB__PL2_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__PL3_REF_CTRL__DIVISOR0 {4} \
   CONFIG.PSU__CRL_APB__PL3_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__QSPI_REF_CTRL__ACT_FREQMHZ {124.998749} \
   CONFIG.PSU__CRL_APB__QSPI_REF_CTRL__DIVISOR0 {12} \
   CONFIG.PSU__CRL_APB__QSPI_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__QSPI_REF_CTRL__FREQMHZ {125} \
   CONFIG.PSU__CRL_APB__QSPI_REF_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRL_APB__RPLL_CTRL__DIV2 {1} \
   CONFIG.PSU__CRL_APB__RPLL_CTRL__FBDIV {90} \
   CONFIG.PSU__CRL_APB__RPLL_CTRL__FRACDATA {0.000000} \
   CONFIG.PSU__CRL_APB__RPLL_CTRL__SRCSEL {PSS_REF_CLK} \
   CONFIG.PSU__CRL_APB__RPLL_FRAC_CFG__ENABLED {0} \
   CONFIG.PSU__CRL_APB__RPLL_TO_FPD_CTRL__DIVISOR0 {3} \
   CONFIG.PSU__CRL_APB__SDIO0_REF_CTRL__DIVISOR0 {7} \
   CONFIG.PSU__CRL_APB__SDIO0_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__SDIO1_REF_CTRL__ACT_FREQMHZ {187.498123} \
   CONFIG.PSU__CRL_APB__SDIO1_REF_CTRL__DIVISOR0 {8} \
   CONFIG.PSU__CRL_APB__SDIO1_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__SDIO1_REF_CTRL__FREQMHZ {200} \
   CONFIG.PSU__CRL_APB__SDIO1_REF_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRL_APB__SPI0_REF_CTRL__DIVISOR0 {7} \
   CONFIG.PSU__CRL_APB__SPI0_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__SPI1_REF_CTRL__DIVISOR0 {7} \
   CONFIG.PSU__CRL_APB__SPI1_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__TIMESTAMP_REF_CTRL__ACT_FREQMHZ {99.999001} \
   CONFIG.PSU__CRL_APB__TIMESTAMP_REF_CTRL__DIVISOR0 {15} \
   CONFIG.PSU__CRL_APB__TIMESTAMP_REF_CTRL__FREQMHZ {100} \
   CONFIG.PSU__CRL_APB__TIMESTAMP_REF_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRL_APB__UART0_REF_CTRL__ACT_FREQMHZ {99.999001} \
   CONFIG.PSU__CRL_APB__UART0_REF_CTRL__DIVISOR0 {15} \
   CONFIG.PSU__CRL_APB__UART0_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__UART0_REF_CTRL__FREQMHZ {100} \
   CONFIG.PSU__CRL_APB__UART0_REF_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRL_APB__UART1_REF_CTRL__DIVISOR0 {15} \
   CONFIG.PSU__CRL_APB__UART1_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__UART1_REF_CTRL__FREQMHZ {100} \
   CONFIG.PSU__CRL_APB__UART1_REF_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRL_APB__USB0_BUS_REF_CTRL__ACT_FREQMHZ {249.997498} \
   CONFIG.PSU__CRL_APB__USB0_BUS_REF_CTRL__DIVISOR0 {6} \
   CONFIG.PSU__CRL_APB__USB0_BUS_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__USB0_BUS_REF_CTRL__FREQMHZ {250} \
   CONFIG.PSU__CRL_APB__USB0_BUS_REF_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRL_APB__USB1_BUS_REF_CTRL__DIVISOR0 {6} \
   CONFIG.PSU__CRL_APB__USB1_BUS_REF_CTRL__DIVISOR1 {1} \
   CONFIG.PSU__CRL_APB__USB3_DUAL_REF_CTRL__ACT_FREQMHZ {19.999800} \
   CONFIG.PSU__CRL_APB__USB3_DUAL_REF_CTRL__DIVISOR0 {25} \
   CONFIG.PSU__CRL_APB__USB3_DUAL_REF_CTRL__DIVISOR1 {3} \
   CONFIG.PSU__CRL_APB__USB3_DUAL_REF_CTRL__FREQMHZ {20} \
   CONFIG.PSU__CRL_APB__USB3_DUAL_REF_CTRL__SRCSEL {IOPLL} \
   CONFIG.PSU__CRL_APB__USB3__ENABLE {1} \
   CONFIG.PSU__CSUPMU__PERIPHERAL__VALID {1} \
   CONFIG.PSU__DDRC__ADDR_MIRROR {0} \
   CONFIG.PSU__DDRC__BANK_ADDR_COUNT {2} \
   CONFIG.PSU__DDRC__BG_ADDR_COUNT {1} \
   CONFIG.PSU__DDRC__BRC_MAPPING {ROW_BANK_COL} \
   CONFIG.PSU__DDRC__BUS_WIDTH {64 Bit} \
   CONFIG.PSU__DDRC__CL {15} \
   CONFIG.PSU__DDRC__CLOCK_STOP_EN {0} \
   CONFIG.PSU__DDRC__COL_ADDR_COUNT {10} \
   CONFIG.PSU__DDRC__COMPONENTS {UDIMM} \
   CONFIG.PSU__DDRC__CWL {11} \
   CONFIG.PSU__DDRC__DDR3L_T_REF_RANGE {NA} \
   CONFIG.PSU__DDRC__DDR3_T_REF_RANGE {NA} \
   CONFIG.PSU__DDRC__DDR4_ADDR_MAPPING {0} \
   CONFIG.PSU__DDRC__DDR4_CAL_MODE_ENABLE {0} \
   CONFIG.PSU__DDRC__DDR4_CRC_CONTROL {0} \
   CONFIG.PSU__DDRC__DDR4_T_REF_MODE {0} \
   CONFIG.PSU__DDRC__DDR4_T_REF_RANGE {Normal (0-85)} \
   CONFIG.PSU__DDRC__DEEP_PWR_DOWN_EN {0} \
   CONFIG.PSU__DDRC__DEVICE_CAPACITY {8192 MBits} \
   CONFIG.PSU__DDRC__DIMM_ADDR_MIRROR {0} \
   CONFIG.PSU__DDRC__DM_DBI {DM_NO_DBI} \
   CONFIG.PSU__DDRC__DQMAP_0_3 {0} \
   CONFIG.PSU__DDRC__DQMAP_12_15 {0} \
   CONFIG.PSU__DDRC__DQMAP_16_19 {0} \
   CONFIG.PSU__DDRC__DQMAP_20_23 {0} \
   CONFIG.PSU__DDRC__DQMAP_24_27 {0} \
   CONFIG.PSU__DDRC__DQMAP_28_31 {0} \
   CONFIG.PSU__DDRC__DQMAP_32_35 {0} \
   CONFIG.PSU__DDRC__DQMAP_36_39 {0} \
   CONFIG.PSU__DDRC__DQMAP_40_43 {0} \
   CONFIG.PSU__DDRC__DQMAP_44_47 {0} \
   CONFIG.PSU__DDRC__DQMAP_48_51 {0} \
   CONFIG.PSU__DDRC__DQMAP_4_7 {0} \
   CONFIG.PSU__DDRC__DQMAP_52_55 {0} \
   CONFIG.PSU__DDRC__DQMAP_56_59 {0} \
   CONFIG.PSU__DDRC__DQMAP_60_63 {0} \
   CONFIG.PSU__DDRC__DQMAP_64_67 {0} \
   CONFIG.PSU__DDRC__DQMAP_68_71 {0} \
   CONFIG.PSU__DDRC__DQMAP_8_11 {0} \
   CONFIG.PSU__DDRC__DRAM_WIDTH {16 Bits} \
   CONFIG.PSU__DDRC__ECC {Disabled} \
   CONFIG.PSU__DDRC__ENABLE_LP4_HAS_ECC_COMP {0} \
   CONFIG.PSU__DDRC__ENABLE_LP4_SLOWBOOT {0} \
   CONFIG.PSU__DDRC__FGRM {1X} \
   CONFIG.PSU__DDRC__LPDDR3_T_REF_RANGE {NA} \
   CONFIG.PSU__DDRC__LPDDR4_T_REF_RANGE {NA} \
   CONFIG.PSU__DDRC__LP_ASR {manual normal} \
   CONFIG.PSU__DDRC__MEMORY_TYPE {DDR 4} \
   CONFIG.PSU__DDRC__PARITY_ENABLE {0} \
   CONFIG.PSU__DDRC__PER_BANK_REFRESH {0} \
   CONFIG.PSU__DDRC__PHY_DBI_MODE {0} \
   CONFIG.PSU__DDRC__RANK_ADDR_COUNT {0} \
   CONFIG.PSU__DDRC__ROW_ADDR_COUNT {16} \
   CONFIG.PSU__DDRC__SB_TARGET {15-15-15} \
   CONFIG.PSU__DDRC__SELF_REF_ABORT {0} \
   CONFIG.PSU__DDRC__SPEED_BIN {DDR4_2133P} \
   CONFIG.PSU__DDRC__STATIC_RD_MODE {0} \
   CONFIG.PSU__DDRC__TRAIN_DATA_EYE {1} \
   CONFIG.PSU__DDRC__TRAIN_READ_GATE {1} \
   CONFIG.PSU__DDRC__TRAIN_WRITE_LEVEL {1} \
   CONFIG.PSU__DDRC__T_FAW {30.0} \
   CONFIG.PSU__DDRC__T_RAS_MIN {33} \
   CONFIG.PSU__DDRC__T_RC {46.5} \
   CONFIG.PSU__DDRC__T_RCD {15} \
   CONFIG.PSU__DDRC__T_RP {15} \
   CONFIG.PSU__DDRC__VENDOR_PART {OTHERS} \
   CONFIG.PSU__DDRC__VREF {1} \
   CONFIG.PSU__DDR_HIGH_ADDRESS_GUI_ENABLE {1} \
   CONFIG.PSU__DDR__INTERFACE__FREQMHZ {533.000} \
   CONFIG.PSU__DLL__ISUSED {1} \
   CONFIG.PSU__ENET0__GRP_MDIO__ENABLE {0} \
   CONFIG.PSU__ENET3__FIFO__ENABLE {0} \
   CONFIG.PSU__ENET3__GRP_MDIO__ENABLE {1} \
   CONFIG.PSU__ENET3__GRP_MDIO__IO {MIO 76 .. 77} \
   CONFIG.PSU__ENET3__PERIPHERAL__ENABLE {1} \
   CONFIG.PSU__ENET3__PERIPHERAL__IO {MIO 64 .. 75} \
   CONFIG.PSU__ENET3__PTP__ENABLE {0} \
   CONFIG.PSU__ENET3__TSU__ENABLE {0} \
   CONFIG.PSU__FPDMASTERS_COHERENCY {0} \
   CONFIG.PSU__FPD_SLCR__WDT1__ACT_FREQMHZ {99.999001} \
   CONFIG.PSU__FPD_SLCR__WDT1__FREQMHZ {99.999001} \
   CONFIG.PSU__FPD_SLCR__WDT_CLK_SEL__SELECT {APB} \
   CONFIG.PSU__FPGA_PL0_ENABLE {1} \
   CONFIG.PSU__GEM3_COHERENCY {0} \
   CONFIG.PSU__GEM3_ROUTE_THROUGH_FPD {0} \
   CONFIG.PSU__GEM__TSU__ENABLE {0} \
   CONFIG.PSU__GPIO0_MIO__IO {MIO 0 .. 25} \
   CONFIG.PSU__GPIO0_MIO__PERIPHERAL__ENABLE {1} \
   CONFIG.PSU__GPIO1_MIO__IO {MIO 26 .. 51} \
   CONFIG.PSU__GPIO1_MIO__PERIPHERAL__ENABLE {1} \
   CONFIG.PSU__HIGH_ADDRESS__ENABLE {1} \
   CONFIG.PSU__I2C0__PERIPHERAL__ENABLE {1} \
   CONFIG.PSU__I2C0__PERIPHERAL__IO {MIO 14 .. 15} \
   CONFIG.PSU__I2C1__PERIPHERAL__ENABLE {1} \
   CONFIG.PSU__I2C1__PERIPHERAL__IO {MIO 16 .. 17} \
   CONFIG.PSU__IOU_SLCR__IOU_TTC_APB_CLK__TTC0_SEL {APB} \
   CONFIG.PSU__IOU_SLCR__IOU_TTC_APB_CLK__TTC1_SEL {APB} \
   CONFIG.PSU__IOU_SLCR__IOU_TTC_APB_CLK__TTC2_SEL {APB} \
   CONFIG.PSU__IOU_SLCR__IOU_TTC_APB_CLK__TTC3_SEL {APB} \
   CONFIG.PSU__IOU_SLCR__TTC0__ACT_FREQMHZ {100.000000} \
   CONFIG.PSU__IOU_SLCR__TTC0__FREQMHZ {100.000000} \
   CONFIG.PSU__IOU_SLCR__TTC1__ACT_FREQMHZ {100.000000} \
   CONFIG.PSU__IOU_SLCR__TTC1__FREQMHZ {100.000000} \
   CONFIG.PSU__IOU_SLCR__TTC2__ACT_FREQMHZ {100.000000} \
   CONFIG.PSU__IOU_SLCR__TTC2__FREQMHZ {100.000000} \
   CONFIG.PSU__IOU_SLCR__TTC3__ACT_FREQMHZ {100.000000} \
   CONFIG.PSU__IOU_SLCR__TTC3__FREQMHZ {100.000000} \
   CONFIG.PSU__IOU_SLCR__WDT0__ACT_FREQMHZ {99.999001} \
   CONFIG.PSU__IOU_SLCR__WDT0__FREQMHZ {99.999001} \
   CONFIG.PSU__IOU_SLCR__WDT_CLK_SEL__SELECT {APB} \
   CONFIG.PSU__LPD_SLCR__CSUPMU__ACT_FREQMHZ {100.000000} \
   CONFIG.PSU__LPD_SLCR__CSUPMU__FREQMHZ {100.000000} \
   CONFIG.PSU__MAXIGP0__DATA_WIDTH {128} \
   CONFIG.PSU__MAXIGP1__DATA_WIDTH {128} \
   CONFIG.PSU__MAXIGP2__DATA_WIDTH {32} \
   CONFIG.PSU__OVERRIDE__BASIC_CLOCK {0} \
   CONFIG.PSU__PL_CLK0_BUF {TRUE} \
   CONFIG.PSU__PMU_COHERENCY {0} \
   CONFIG.PSU__PMU__AIBACK__ENABLE {0} \
   CONFIG.PSU__PMU__EMIO_GPI__ENABLE {0} \
   CONFIG.PSU__PMU__EMIO_GPO__ENABLE {0} \
   CONFIG.PSU__PMU__GPI0__ENABLE {0} \
   CONFIG.PSU__PMU__GPI1__ENABLE {0} \
   CONFIG.PSU__PMU__GPI2__ENABLE {0} \
   CONFIG.PSU__PMU__GPI3__ENABLE {0} \
   CONFIG.PSU__PMU__GPI4__ENABLE {0} \
   CONFIG.PSU__PMU__GPI5__ENABLE {0} \
   CONFIG.PSU__PMU__GPO0__ENABLE {1} \
   CONFIG.PSU__PMU__GPO0__IO {MIO 32} \
   CONFIG.PSU__PMU__GPO1__ENABLE {1} \
   CONFIG.PSU__PMU__GPO1__IO {MIO 33} \
   CONFIG.PSU__PMU__GPO2__ENABLE {1} \
   CONFIG.PSU__PMU__GPO2__IO {MIO 34} \
   CONFIG.PSU__PMU__GPO2__POLARITY {low} \
   CONFIG.PSU__PMU__GPO3__ENABLE {1} \
   CONFIG.PSU__PMU__GPO3__IO {MIO 35} \
   CONFIG.PSU__PMU__GPO3__POLARITY {low} \
   CONFIG.PSU__PMU__GPO4__ENABLE {1} \
   CONFIG.PSU__PMU__GPO4__IO {MIO 36} \
   CONFIG.PSU__PMU__GPO4__POLARITY {low} \
   CONFIG.PSU__PMU__GPO5__ENABLE {1} \
   CONFIG.PSU__PMU__GPO5__IO {MIO 37} \
   CONFIG.PSU__PMU__GPO5__POLARITY {low} \
   CONFIG.PSU__PMU__PERIPHERAL__ENABLE {1} \
   CONFIG.PSU__PMU__PLERROR__ENABLE {0} \
   CONFIG.PSU__PRESET_APPLIED {1} \
   CONFIG.PSU__PROTECTION__MASTERS {USB1:NonSecure;0|USB0:NonSecure;1|S_AXI_LPD:NA;0|S_AXI_HPC1_FPD:NA;1|S_AXI_HPC0_FPD:NA;1|S_AXI_HP3_FPD:NA;0|S_AXI_HP2_FPD:NA;0|S_AXI_HP1_FPD:NA;0|S_AXI_HP0_FPD:NA;0|S_AXI_ACP:NA;0|S_AXI_ACE:NA;0|SD1:NonSecure;1|SD0:NonSecure;0|SATA1:NonSecure;1|SATA0:NonSecure;1|RPU1:Secure;1|RPU0:Secure;1|QSPI:NonSecure;1|PMU:NA;1|PCIe:NonSecure;0|NAND:NonSecure;0|LDMA:NonSecure;1|GPU:NonSecure;1|GEM3:NonSecure;1|GEM2:NonSecure;0|GEM1:NonSecure;0|GEM0:NonSecure;0|FDMA:NonSecure;1|DP:NonSecure;0|DAP:NA;1|Coresight:NA;1|CSU:NA;1|APU:NA;1} \
   CONFIG.PSU__PROTECTION__SLAVES { \
     LPD;USB3_1_XHCI;FE300000;FE3FFFFF;0|LPD;USB3_1;FF9E0000;FF9EFFFF;0|LPD;USB3_0_XHCI;FE200000;FE2FFFFF;1|LPD;USB3_0;FF9D0000;FF9DFFFF;1|LPD;UART1;FF010000;FF01FFFF;0|LPD;UART0;FF000000;FF00FFFF;1|LPD;TTC3;FF140000;FF14FFFF;1|LPD;TTC2;FF130000;FF13FFFF;1|LPD;TTC1;FF120000;FF12FFFF;1|LPD;TTC0;FF110000;FF11FFFF;1|FPD;SWDT1;FD4D0000;FD4DFFFF;1|LPD;SWDT0;FF150000;FF15FFFF;1|LPD;SPI1;FF050000;FF05FFFF;0|LPD;SPI0;FF040000;FF04FFFF;0|FPD;SMMU_REG;FD5F0000;FD5FFFFF;1|FPD;SMMU;FD800000;FDFFFFFF;1|FPD;SIOU;FD3D0000;FD3DFFFF;1|FPD;SERDES;FD400000;FD47FFFF;1|LPD;SD1;FF170000;FF17FFFF;1|LPD;SD0;FF160000;FF16FFFF;0|FPD;SATA;FD0C0000;FD0CFFFF;1|LPD;RTC;FFA60000;FFA6FFFF;1|LPD;RSA_CORE;FFCE0000;FFCEFFFF;1|LPD;RPU;FF9A0000;FF9AFFFF;1|LPD;R5_TCM_RAM_GLOBAL;FFE00000;FFE3FFFF;1|LPD;R5_1_Instruction_Cache;FFEC0000;FFECFFFF;1|LPD;R5_1_Data_Cache;FFED0000;FFEDFFFF;1|LPD;R5_1_BTCM_GLOBAL;FFEB0000;FFEBFFFF;1|LPD;R5_1_ATCM_GLOBAL;FFE90000;FFE9FFFF;1|LPD;R5_0_Instruction_Cache;FFE40000;FFE4FFFF;1|LPD;R5_0_Data_Cache;FFE50000;FFE5FFFF;1|LPD;R5_0_BTCM_GLOBAL;FFE20000;FFE2FFFF;1|LPD;R5_0_ATCM_GLOBAL;FFE00000;FFE0FFFF;1|LPD;QSPI_Linear_Address;C0000000;DFFFFFFF;1|LPD;QSPI;FF0F0000;FF0FFFFF;1|LPD;PMU_RAM;FFDC0000;FFDDFFFF;1|LPD;PMU_GLOBAL;FFD80000;FFDBFFFF;1|FPD;PCIE_MAIN;FD0E0000;FD0EFFFF;0|FPD;PCIE_LOW;E0000000;EFFFFFFF;0|FPD;PCIE_HIGH2;8000000000;BFFFFFFFFF;0|FPD;PCIE_HIGH1;600000000;7FFFFFFFF;0|FPD;PCIE_DMA;FD0F0000;FD0FFFFF;0|FPD;PCIE_ATTRIB;FD480000;FD48FFFF;0|LPD;OCM_XMPU_CFG;FFA70000;FFA7FFFF;1|LPD;OCM_SLCR;FF960000;FF96FFFF;1|OCM;OCM;FFFC0000;FFFFFFFF;1|LPD;NAND;FF100000;FF10FFFF;0|LPD;MBISTJTAG;FFCF0000;FFCFFFFF;1|LPD;LPD_XPPU_SINK;FF9C0000;FF9CFFFF;1|LPD;LPD_XPPU;FF980000;FF98FFFF;1|LPD;LPD_SLCR_SECURE;FF4B0000;FF4DFFFF;1|LPD;LPD_SLCR;FF410000;FF4AFFFF;1|LPD;LPD_GPV;FE100000;FE1FFFFF;1|LPD;LPD_DMA_7;FFAF0000;FFAFFFFF;1|LPD;LPD_DMA_6;FFAE0000;FFAEFFFF;1|LPD;LPD_DMA_5;FFAD0000;FFADFFFF;1|LPD;LPD_DMA_4;FFAC0000;FFACFFFF;1|LPD;LPD_DMA_3;FFAB0000;FFABFFFF;1|LPD;LPD_DMA_2;FFAA0000;FFAAFFFF;1|LPD;LPD_DMA_1;FFA90000;FFA9FFFF;1|LPD;LPD_DMA_0;FFA80000;FFA8FFFF;1|LPD;IPI_CTRL;FF380000;FF3FFFFF;1|LPD;IOU_SLCR;FF180000;FF23FFFF;1|LPD;IOU_SECURE_SLCR;FF240000;FF24FFFF;1|LPD;IOU_SCNTRS;FF260000;FF26FFFF;1|LPD;IOU_SCNTR;FF250000;FF25FFFF;1|LPD;IOU_GPV;FE000000;FE0FFFFF;1|LPD;I2C1;FF030000;FF03FFFF;1|LPD;I2C0;FF020000;FF02FFFF;1|FPD;GPU;FD4B0000;FD4BFFFF;0|LPD;GPIO;FF0A0000;FF0AFFFF;1|LPD;GEM3;FF0E0000;FF0EFFFF;1|LPD;GEM2;FF0D0000;FF0DFFFF;0|LPD;GEM1;FF0C0000;FF0CFFFF;0|LPD;GEM0;FF0B0000;FF0BFFFF;0|FPD;FPD_XMPU_SINK;FD4F0000;FD4FFFFF;1|FPD;FPD_XMPU_CFG;FD5D0000;FD5DFFFF;1|FPD;FPD_SLCR_SECURE;FD690000;FD6CFFFF;1|FPD;FPD_SLCR;FD610000;FD68FFFF;1|FPD;FPD_DMA_CH7;FD570000;FD57FFFF;1|FPD;FPD_DMA_CH6;FD560000;FD56FFFF;1|FPD;FPD_DMA_CH5;FD550000;FD55FFFF;1|FPD;FPD_DMA_CH4;FD540000;FD54FFFF;1|FPD;FPD_DMA_CH3;FD530000;FD53FFFF;1|FPD;FPD_DMA_CH2;FD520000;FD52FFFF;1|FPD;FPD_DMA_CH1;FD510000;FD51FFFF;1|FPD;FPD_DMA_CH0;FD500000;FD50FFFF;1|LPD;EFUSE;FFCC0000;FFCCFFFF;1|FPD;Display Port;FD4A0000;FD4AFFFF;0|FPD;DPDMA;FD4C0000;FD4CFFFF;0|FPD;DDR_XMPU5_CFG;FD050000;FD05FFFF;1|FPD;DDR_XMPU4_CFG;FD040000;FD04FFFF;1|FPD;DDR_XMPU3_CFG;FD030000;FD03FFFF;1|FPD;DDR_XMPU2_CFG;FD020000;FD02FFFF;1|FPD;DDR_XMPU1_CFG;FD010000;FD01FFFF;1|FPD;DDR_XMPU0_CFG;FD000000;FD00FFFF;1|FPD;DDR_QOS_CTRL;FD090000;FD09FFFF;1|FPD;DDR_PHY;FD080000;FD08FFFF;1|DDR;DDR_LOW;0;7FFFFFFF;1|DDR;DDR_HIGH;800000000;87FFFFFFF;1|FPD;DDDR_CTRL;FD070000;FD070FFF;1|LPD;Coresight;FE800000;FEFFFFFF;1|LPD;CSU_DMA;FFC80000;FFC9FFFF;1|LPD;CSU;FFCA0000;FFCAFFFF;1|LPD;CRL_APB;FF5E0000;FF85FFFF;1|FPD;CRF_APB;FD1A0000;FD2DFFFF;1|FPD;CCI_REG;FD5E0000;FD5EFFFF;1|LPD;CAN1;FF070000;FF07FFFF;0|LPD;CAN0;FF060000;FF06FFFF;0|FPD;APU;FD5C0000;FD5CFFFF;1|LPD;APM_INTC_IOU;FFA20000;FFA2FFFF;1|LPD;APM_FPD_LPD;FFA30000;FFA3FFFF;1|FPD;APM_5;FD490000;FD49FFFF;1|FPD;APM_0;FD0B0000;FD0BFFFF;1|LPD;APM2;FFA10000;FFA1FFFF;1|LPD;APM1;FFA00000;FFA0FFFF;1|LPD;AMS;FFA50000;FFA5FFFF;1|FPD;AFI_5;FD3B0000;FD3BFFFF;1|FPD;AFI_4;FD3A0000;FD3AFFFF;1|FPD;AFI_3;FD390000;FD39FFFF;1|FPD;AFI_2;FD380000;FD38FFFF;1|FPD;AFI_1;FD370000;FD37FFFF;1|FPD;AFI_0;FD360000;FD36FFFF;1|LPD;AFIFM6;FF9B0000;FF9BFFFF;1|FPD;ACPU_GIC;F9010000;F907FFFF;1 \
   } \
   CONFIG.PSU__PSS_REF_CLK__FREQMHZ {33.333} \
   CONFIG.PSU__QSPI_COHERENCY {0} \
   CONFIG.PSU__QSPI_ROUTE_THROUGH_FPD {0} \
   CONFIG.PSU__QSPI__GRP_FBCLK__ENABLE {1} \
   CONFIG.PSU__QSPI__GRP_FBCLK__IO {MIO 6} \
   CONFIG.PSU__QSPI__PERIPHERAL__DATA_MODE {x4} \
   CONFIG.PSU__QSPI__PERIPHERAL__ENABLE {1} \
   CONFIG.PSU__QSPI__PERIPHERAL__IO {MIO 0 .. 12} \
   CONFIG.PSU__QSPI__PERIPHERAL__MODE {Dual Parallel} \
   CONFIG.PSU__SATA__LANE0__ENABLE {0} \
   CONFIG.PSU__SATA__LANE1__ENABLE {1} \
   CONFIG.PSU__SATA__LANE1__IO {GT Lane3} \
   CONFIG.PSU__SATA__PERIPHERAL__ENABLE {1} \
   CONFIG.PSU__SATA__REF_CLK_FREQ {125} \
   CONFIG.PSU__SATA__REF_CLK_SEL {Ref Clk3} \
   CONFIG.PSU__SAXIGP0__DATA_WIDTH {128} \
   CONFIG.PSU__SAXIGP1__DATA_WIDTH {128} \
   CONFIG.PSU__SD1_COHERENCY {0} \
   CONFIG.PSU__SD1_ROUTE_THROUGH_FPD {0} \
   CONFIG.PSU__SD1__DATA_TRANSFER_MODE {8Bit} \
   CONFIG.PSU__SD1__GRP_CD__ENABLE {1} \
   CONFIG.PSU__SD1__GRP_CD__IO {MIO 45} \
   CONFIG.PSU__SD1__GRP_POW__ENABLE {0} \
   CONFIG.PSU__SD1__GRP_WP__ENABLE {0} \
   CONFIG.PSU__SD1__PERIPHERAL__ENABLE {1} \
   CONFIG.PSU__SD1__PERIPHERAL__IO {MIO 39 .. 51} \
   CONFIG.PSU__SD1__RESET__ENABLE {0} \
   CONFIG.PSU__SD1__SLOT_TYPE {SD 3.0} \
   CONFIG.PSU__SWDT0__CLOCK__ENABLE {0} \
   CONFIG.PSU__SWDT0__PERIPHERAL__ENABLE {1} \
   CONFIG.PSU__SWDT0__RESET__ENABLE {0} \
   CONFIG.PSU__SWDT1__CLOCK__ENABLE {0} \
   CONFIG.PSU__SWDT1__PERIPHERAL__ENABLE {1} \
   CONFIG.PSU__SWDT1__RESET__ENABLE {0} \
   CONFIG.PSU__TSU__BUFG_PORT_PAIR {0} \
   CONFIG.PSU__TTC0__CLOCK__ENABLE {0} \
   CONFIG.PSU__TTC0__PERIPHERAL__ENABLE {1} \
   CONFIG.PSU__TTC0__WAVEOUT__ENABLE {0} \
   CONFIG.PSU__TTC1__CLOCK__ENABLE {0} \
   CONFIG.PSU__TTC1__PERIPHERAL__ENABLE {1} \
   CONFIG.PSU__TTC1__WAVEOUT__ENABLE {0} \
   CONFIG.PSU__TTC2__CLOCK__ENABLE {0} \
   CONFIG.PSU__TTC2__PERIPHERAL__ENABLE {1} \
   CONFIG.PSU__TTC2__WAVEOUT__ENABLE {0} \
   CONFIG.PSU__TTC3__CLOCK__ENABLE {0} \
   CONFIG.PSU__TTC3__PERIPHERAL__ENABLE {1} \
   CONFIG.PSU__TTC3__WAVEOUT__ENABLE {0} \
   CONFIG.PSU__UART0__BAUD_RATE {115200} \
   CONFIG.PSU__UART0__MODEM__ENABLE {0} \
   CONFIG.PSU__UART0__PERIPHERAL__ENABLE {1} \
   CONFIG.PSU__UART0__PERIPHERAL__IO {MIO 18 .. 19} \
   CONFIG.PSU__USB0_COHERENCY {0} \
   CONFIG.PSU__USB0__PERIPHERAL__ENABLE {1} \
   CONFIG.PSU__USB0__PERIPHERAL__IO {MIO 52 .. 63} \
   CONFIG.PSU__USB0__REF_CLK_FREQ {26} \
   CONFIG.PSU__USB0__REF_CLK_SEL {Ref Clk2} \
   CONFIG.PSU__USB0__RESET__ENABLE {0} \
   CONFIG.PSU__USB1__RESET__ENABLE {0} \
   CONFIG.PSU__USB2_0__EMIO__ENABLE {0} \
   CONFIG.PSU__USB3_0__EMIO__ENABLE {0} \
   CONFIG.PSU__USB3_0__PERIPHERAL__ENABLE {1} \
   CONFIG.PSU__USB3_0__PERIPHERAL__IO {GT Lane2} \
   CONFIG.PSU__USB__RESET__MODE {Boot Pin} \
   CONFIG.PSU__USB__RESET__POLARITY {Active Low} \
   CONFIG.PSU__USE__IRQ0 {1} \
   CONFIG.PSU__USE__M_AXI_GP0 {1} \
   CONFIG.PSU__USE__M_AXI_GP1 {1} \
   CONFIG.PSU__USE__M_AXI_GP2 {0} \
   CONFIG.PSU__USE__S_AXI_GP0 {1} \
   CONFIG.PSU__USE__S_AXI_GP1 {1} \
   CONFIG.SUBPRESET1 {Custom} \
 ] $zynq_ultra_ps_e_0

  # Create interface connections
  connect_bd_intf_net -intf_net adc2_clk_1 [get_bd_intf_ports adc2_clk] [get_bd_intf_pins usp_rf_data_converter_0/adc2_clk]
  connect_bd_intf_net -intf_net axi_bram_ctrl_0_BRAM_PORTA [get_bd_intf_pins axi_bram_ctrl_0/BRAM_PORTA] [get_bd_intf_pins axi_bram_ctrl_0_bram/BRAM_PORTA]
  connect_bd_intf_net -intf_net axi_dma_0_M_AXIS_MM2S [get_bd_intf_pins axi_dma_gen/M_AXIS_MM2S] [get_bd_intf_pins axis_switch_gen/S00_AXIS]
  connect_bd_intf_net -intf_net axi_dma_avg_M_AXI_S2MM [get_bd_intf_pins axi_dma_avg/M_AXI_S2MM] [get_bd_intf_pins axi_smc_1/S00_AXI]
  connect_bd_intf_net -intf_net axi_dma_buf_M_AXI_S2MM [get_bd_intf_pins axi_dma_buf/M_AXI_S2MM] [get_bd_intf_pins axi_smc_1/S01_AXI]
  connect_bd_intf_net -intf_net axi_dma_gen_M_AXI_MM2S [get_bd_intf_pins axi_dma_gen/M_AXI_MM2S] [get_bd_intf_pins axi_smc_1/S02_AXI]
  connect_bd_intf_net -intf_net axi_dma_tproc_M_AXIS_MM2S [get_bd_intf_pins axi_dma_tproc/M_AXIS_MM2S] [get_bd_intf_pins axis_tproc64x32_x8_0/s0_axis]
  connect_bd_intf_net -intf_net axi_dma_tproc_M_AXI_MM2S [get_bd_intf_pins axi_dma_tproc/M_AXI_MM2S] [get_bd_intf_pins axi_smc_2/S00_AXI]
  connect_bd_intf_net -intf_net axi_dma_tproc_M_AXI_S2MM [get_bd_intf_pins axi_dma_tproc/M_AXI_S2MM] [get_bd_intf_pins axi_smc_2/S01_AXI]
  connect_bd_intf_net -intf_net axi_smc_1_M00_AXI [get_bd_intf_pins axi_smc_1/M00_AXI] [get_bd_intf_pins zynq_ultra_ps_e_0/S_AXI_HPC0_FPD]
  connect_bd_intf_net -intf_net axi_smc_2_M00_AXI [get_bd_intf_pins axi_smc_2/M00_AXI] [get_bd_intf_pins zynq_ultra_ps_e_0/S_AXI_HPC1_FPD]
  connect_bd_intf_net -intf_net axi_smc_M00_AXI [get_bd_intf_pins axi_bram_ctrl_0/S_AXI] [get_bd_intf_pins axi_smc/M00_AXI]
  connect_bd_intf_net -intf_net axi_smc_M01_AXI [get_bd_intf_pins axi_dma_avg/S_AXI_LITE] [get_bd_intf_pins axi_smc/M01_AXI]
  connect_bd_intf_net -intf_net axi_smc_M02_AXI [get_bd_intf_pins axi_dma_buf/S_AXI_LITE] [get_bd_intf_pins axi_smc/M02_AXI]
  connect_bd_intf_net -intf_net axi_smc_M03_AXI [get_bd_intf_pins axi_dma_gen/S_AXI_LITE] [get_bd_intf_pins axi_smc/M03_AXI]
  connect_bd_intf_net -intf_net axi_smc_M04_AXI [get_bd_intf_pins axi_dma_tproc/S_AXI_LITE] [get_bd_intf_pins axi_smc/M04_AXI]
  connect_bd_intf_net -intf_net axi_smc_M05_AXI [get_bd_intf_pins axi_smc/M05_AXI] [get_bd_intf_pins axis_avg_buffer_0/s_axi]
  connect_bd_intf_net -intf_net axi_smc_M06_AXI [get_bd_intf_pins axi_smc/M06_AXI] [get_bd_intf_pins axis_avg_buffer_1/s_axi]
  connect_bd_intf_net -intf_net axi_smc_M07_AXI [get_bd_intf_pins axi_smc/M07_AXI] [get_bd_intf_pins axis_avg_buffer_2/s_axi]
  connect_bd_intf_net -intf_net axi_smc_M08_AXI [get_bd_intf_pins axi_smc/M08_AXI] [get_bd_intf_pins axis_avg_buffer_3/s_axi]
  connect_bd_intf_net -intf_net axi_smc_M09_AXI [get_bd_intf_pins axi_smc/M09_AXI] [get_bd_intf_pins axis_constant_iq_0/s_axi]
  connect_bd_intf_net -intf_net axi_smc_M10_AXI [get_bd_intf_pins axi_smc/M10_AXI] [get_bd_intf_pins axis_constant_iq_1/s_axi]
  connect_bd_intf_net -intf_net axi_smc_M11_AXI [get_bd_intf_pins axi_smc/M11_AXI] [get_bd_intf_pins axis_constant_iq_2/s_axi]
  connect_bd_intf_net -intf_net axi_smc_M12_AXI [get_bd_intf_pins axi_smc/M12_AXI] [get_bd_intf_pins axis_constant_iq_3/s_axi]
  connect_bd_intf_net -intf_net axi_smc_M13_AXI [get_bd_intf_pins axi_smc/M13_AXI] [get_bd_intf_pins axis_sg_mux4_v2_6/s_axi]
  connect_bd_intf_net -intf_net axi_smc_M14_AXI [get_bd_intf_pins axi_smc/M14_AXI] [get_bd_intf_pins axis_sg_int4_v1_0/s_axi]
  connect_bd_intf_net -intf_net axi_smc_M15_AXI [get_bd_intf_pins axi_smc/M15_AXI] [get_bd_intf_pins axis_sg_int4_v1_1/s_axi]
  connect_bd_intf_net -intf_net axis_avg_buffer_0_m0_axis [get_bd_intf_pins axis_avg_buffer_0/m0_axis] [get_bd_intf_pins axis_switch_avg/S00_AXIS]
  connect_bd_intf_net -intf_net axis_avg_buffer_0_m1_axis [get_bd_intf_pins axis_avg_buffer_0/m1_axis] [get_bd_intf_pins axis_switch_buf/S00_AXIS]
  connect_bd_intf_net -intf_net axis_avg_buffer_0_m2_axis [get_bd_intf_pins axis_avg_buffer_0/m2_axis] [get_bd_intf_pins axis_cc_avg_0/S_AXIS]
  connect_bd_intf_net -intf_net axis_avg_buffer_1_m0_axis [get_bd_intf_pins axis_avg_buffer_1/m0_axis] [get_bd_intf_pins axis_switch_avg/S01_AXIS]
  connect_bd_intf_net -intf_net axis_avg_buffer_1_m1_axis [get_bd_intf_pins axis_avg_buffer_1/m1_axis] [get_bd_intf_pins axis_switch_buf/S01_AXIS]
  connect_bd_intf_net -intf_net axis_avg_buffer_1_m2_axis [get_bd_intf_pins axis_avg_buffer_1/m2_axis] [get_bd_intf_pins axis_cc_avg_1/S_AXIS]
  connect_bd_intf_net -intf_net axis_avg_buffer_2_m0_axis [get_bd_intf_pins axis_avg_buffer_2/m0_axis] [get_bd_intf_pins axis_switch_avg/S02_AXIS]
  connect_bd_intf_net -intf_net axis_avg_buffer_2_m1_axis [get_bd_intf_pins axis_avg_buffer_2/m1_axis] [get_bd_intf_pins axis_switch_buf/S02_AXIS]
  connect_bd_intf_net -intf_net axis_avg_buffer_2_m2_axis [get_bd_intf_pins axis_avg_buffer_2/m2_axis] [get_bd_intf_pins axis_cc_avg_2/S_AXIS]
  connect_bd_intf_net -intf_net axis_avg_buffer_3_m0_axis [get_bd_intf_pins axis_avg_buffer_3/m0_axis] [get_bd_intf_pins axis_switch_avg/S03_AXIS]
  connect_bd_intf_net -intf_net axis_avg_buffer_3_m1_axis [get_bd_intf_pins axis_avg_buffer_3/m1_axis] [get_bd_intf_pins axis_switch_buf/S03_AXIS]
  connect_bd_intf_net -intf_net axis_avg_buffer_3_m2_axis [get_bd_intf_pins axis_avg_buffer_3/m2_axis] [get_bd_intf_pins axis_cc_avg_3/S_AXIS]
  connect_bd_intf_net -intf_net axis_cc_avg_0_M_AXIS [get_bd_intf_pins axis_cc_avg_0/M_AXIS] [get_bd_intf_pins axis_tproc64x32_x8_0/s1_axis]
  connect_bd_intf_net -intf_net axis_cc_avg_1_M_AXIS [get_bd_intf_pins axis_cc_avg_1/M_AXIS] [get_bd_intf_pins axis_tproc64x32_x8_0/s2_axis]
  connect_bd_intf_net -intf_net axis_cc_avg_2_M_AXIS [get_bd_intf_pins axis_cc_avg_2/M_AXIS] [get_bd_intf_pins axis_tproc64x32_x8_0/s3_axis]
  connect_bd_intf_net -intf_net axis_cc_avg_3_M_AXIS [get_bd_intf_pins axis_cc_avg_3/M_AXIS] [get_bd_intf_pins axis_tproc64x32_x8_0/s4_axis]
  connect_bd_intf_net -intf_net axis_cc_sg_0_M_AXIS [get_bd_intf_pins axis_cc_sg_0/M_AXIS] [get_bd_intf_pins axis_sg_int4_v1_0/s1_axis]
  connect_bd_intf_net -intf_net axis_cc_sg_1_M_AXIS [get_bd_intf_pins axis_cc_sg_1/M_AXIS] [get_bd_intf_pins axis_sg_int4_v1_1/s1_axis]
  connect_bd_intf_net -intf_net axis_cc_sg_2_M_AXIS [get_bd_intf_pins axis_cc_sg_2/M_AXIS] [get_bd_intf_pins axis_sg_int4_v1_2/s1_axis]
  connect_bd_intf_net -intf_net axis_cc_sg_3_M_AXIS [get_bd_intf_pins axis_cc_sg_3/M_AXIS] [get_bd_intf_pins axis_sg_int4_v1_3/s1_axis]
  connect_bd_intf_net -intf_net axis_cc_sg_4_M_AXIS [get_bd_intf_pins axis_cc_sg_4/M_AXIS] [get_bd_intf_pins axis_signal_gen_v6_4/s1_axis]
  connect_bd_intf_net -intf_net axis_cc_sg_5_M_AXIS [get_bd_intf_pins axis_cc_sg_5/M_AXIS] [get_bd_intf_pins axis_signal_gen_v6_5/s1_axis]
  connect_bd_intf_net -intf_net axis_cc_sg_6_M_AXIS [get_bd_intf_pins axis_cc_sg_6/M_AXIS] [get_bd_intf_pins axis_sg_mux4_v2_6/s_axis]
  connect_bd_intf_net -intf_net axis_constant_iq_0_m_axis [get_bd_intf_pins axis_constant_iq_0/m_axis] [get_bd_intf_pins usp_rf_data_converter_0/s10_axis]
  connect_bd_intf_net -intf_net axis_constant_iq_1_m_axis [get_bd_intf_pins axis_constant_iq_1/m_axis] [get_bd_intf_pins usp_rf_data_converter_0/s11_axis]
  connect_bd_intf_net -intf_net axis_constant_iq_2_m_axis [get_bd_intf_pins axis_constant_iq_2/m_axis] [get_bd_intf_pins usp_rf_data_converter_0/s12_axis]
  connect_bd_intf_net -intf_net axis_constant_iq_3_m_axis [get_bd_intf_pins axis_constant_iq_3/m_axis] [get_bd_intf_pins usp_rf_data_converter_0/s13_axis]
  connect_bd_intf_net -intf_net axis_pfb_readout_v2_0_m0_axis [get_bd_intf_pins axis_avg_buffer_0/s_axis] [get_bd_intf_pins axis_pfb_readout_v2_0/m0_axis]
  connect_bd_intf_net -intf_net axis_pfb_readout_v2_0_m1_axis [get_bd_intf_pins axis_avg_buffer_1/s_axis] [get_bd_intf_pins axis_pfb_readout_v2_0/m1_axis]
  connect_bd_intf_net -intf_net axis_pfb_readout_v2_0_m2_axis [get_bd_intf_pins axis_avg_buffer_2/s_axis] [get_bd_intf_pins axis_pfb_readout_v2_0/m2_axis]
  connect_bd_intf_net -intf_net axis_pfb_readout_v2_0_m3_axis [get_bd_intf_pins axis_avg_buffer_3/s_axis] [get_bd_intf_pins axis_pfb_readout_v2_0/m3_axis]
  connect_bd_intf_net -intf_net axis_register_slice_0_m_axis [get_bd_intf_pins axis_register_slice_0/m_axis] [get_bd_intf_pins usp_rf_data_converter_0/s30_axis]
  connect_bd_intf_net -intf_net axis_register_slice_1_m_axis [get_bd_intf_pins axis_register_slice_1/m_axis] [get_bd_intf_pins usp_rf_data_converter_0/s31_axis]
  connect_bd_intf_net -intf_net axis_sg_int4_v1_0_m_axis [get_bd_intf_pins axis_sg_int4_v1_0/m_axis] [get_bd_intf_pins usp_rf_data_converter_0/s20_axis]
  connect_bd_intf_net -intf_net axis_sg_int4_v1_1_m_axis [get_bd_intf_pins axis_sg_int4_v1_1/m_axis] [get_bd_intf_pins usp_rf_data_converter_0/s21_axis]
  connect_bd_intf_net -intf_net axis_sg_int4_v1_2_m_axis [get_bd_intf_pins axis_sg_int4_v1_2/m_axis] [get_bd_intf_pins usp_rf_data_converter_0/s22_axis]
  connect_bd_intf_net -intf_net axis_sg_int4_v1_3_m_axis [get_bd_intf_pins axis_sg_int4_v1_3/m_axis] [get_bd_intf_pins usp_rf_data_converter_0/s23_axis]
  connect_bd_intf_net -intf_net axis_sg_mux4_v2_0_m_axis [get_bd_intf_pins axis_sg_mux4_v2_6/m_axis] [get_bd_intf_pins usp_rf_data_converter_0/s00_axis]
  connect_bd_intf_net -intf_net axis_signal_gen_v6_4_m_axis [get_bd_intf_pins axis_register_slice_0/s_axis] [get_bd_intf_pins axis_signal_gen_v6_4/m_axis]
  connect_bd_intf_net -intf_net axis_signal_gen_v6_5_m_axis [get_bd_intf_pins axis_register_slice_1/s_axis] [get_bd_intf_pins axis_signal_gen_v6_5/m_axis]
  connect_bd_intf_net -intf_net axis_switch_0_M00_AXIS [get_bd_intf_pins axis_sg_int4_v1_0/s0_axis] [get_bd_intf_pins axis_switch_gen/M00_AXIS]
  connect_bd_intf_net -intf_net axis_switch_0_M01_AXIS [get_bd_intf_pins axis_sg_int4_v1_1/s0_axis] [get_bd_intf_pins axis_switch_gen/M01_AXIS]
  connect_bd_intf_net -intf_net axis_switch_0_M02_AXIS [get_bd_intf_pins axis_sg_int4_v1_2/s0_axis] [get_bd_intf_pins axis_switch_gen/M02_AXIS]
  connect_bd_intf_net -intf_net axis_switch_0_M03_AXIS [get_bd_intf_pins axis_sg_int4_v1_3/s0_axis] [get_bd_intf_pins axis_switch_gen/M03_AXIS]
  connect_bd_intf_net -intf_net axis_switch_avg_M00_AXIS [get_bd_intf_pins axi_dma_avg/S_AXIS_S2MM] [get_bd_intf_pins axis_switch_avg/M00_AXIS]
  connect_bd_intf_net -intf_net axis_switch_buf_M00_AXIS [get_bd_intf_pins axi_dma_buf/S_AXIS_S2MM] [get_bd_intf_pins axis_switch_buf/M00_AXIS]
  connect_bd_intf_net -intf_net axis_switch_gen_M04_AXIS [get_bd_intf_pins axis_signal_gen_v6_4/s0_axis] [get_bd_intf_pins axis_switch_gen/M04_AXIS]
  connect_bd_intf_net -intf_net axis_switch_gen_M05_AXIS [get_bd_intf_pins axis_signal_gen_v6_5/s0_axis] [get_bd_intf_pins axis_switch_gen/M05_AXIS]
  connect_bd_intf_net -intf_net axis_tproc64x32_x8_0_m0_axis [get_bd_intf_pins axi_dma_tproc/S_AXIS_S2MM] [get_bd_intf_pins axis_tproc64x32_x8_0/m0_axis]
  connect_bd_intf_net -intf_net axis_tproc64x32_x8_0_m1_axis [get_bd_intf_pins axis_cc_sg_0/S_AXIS] [get_bd_intf_pins axis_tproc64x32_x8_0/m1_axis]
  connect_bd_intf_net -intf_net axis_tproc64x32_x8_0_m2_axis [get_bd_intf_pins axis_cc_sg_1/S_AXIS] [get_bd_intf_pins axis_tproc64x32_x8_0/m2_axis]
  connect_bd_intf_net -intf_net axis_tproc64x32_x8_0_m3_axis [get_bd_intf_pins axis_cc_sg_2/S_AXIS] [get_bd_intf_pins axis_tproc64x32_x8_0/m3_axis]
  connect_bd_intf_net -intf_net axis_tproc64x32_x8_0_m4_axis [get_bd_intf_pins axis_cc_sg_3/S_AXIS] [get_bd_intf_pins axis_tproc64x32_x8_0/m4_axis]
  connect_bd_intf_net -intf_net axis_tproc64x32_x8_0_m5_axis [get_bd_intf_pins axis_cc_sg_4/S_AXIS] [get_bd_intf_pins axis_tproc64x32_x8_0/m5_axis]
  connect_bd_intf_net -intf_net axis_tproc64x32_x8_0_m6_axis [get_bd_intf_pins axis_cc_sg_5/S_AXIS] [get_bd_intf_pins axis_tproc64x32_x8_0/m6_axis]
  connect_bd_intf_net -intf_net axis_tproc64x32_x8_0_m7_axis [get_bd_intf_pins axis_cc_sg_6/S_AXIS] [get_bd_intf_pins axis_tproc64x32_x8_0/m7_axis]
  connect_bd_intf_net -intf_net axis_tproc64x32_x8_0_m8_axis [get_bd_intf_pins axis_set_reg_0/s_axis] [get_bd_intf_pins axis_tproc64x32_x8_0/m8_axis]
  connect_bd_intf_net -intf_net dac2_clk_1 [get_bd_intf_ports dac2_clk] [get_bd_intf_pins usp_rf_data_converter_0/dac2_clk]
  connect_bd_intf_net -intf_net ps8_0_axi_periph_M00_AXI [get_bd_intf_pins axis_sg_int4_v1_2/s_axi] [get_bd_intf_pins ps8_0_axi_periph/M00_AXI]
  connect_bd_intf_net -intf_net ps8_0_axi_periph_M01_AXI [get_bd_intf_pins axis_sg_int4_v1_3/s_axi] [get_bd_intf_pins ps8_0_axi_periph/M01_AXI]
  connect_bd_intf_net -intf_net ps8_0_axi_periph_M02_AXI [get_bd_intf_pins axis_signal_gen_v6_4/s_axi] [get_bd_intf_pins ps8_0_axi_periph/M02_AXI]
  connect_bd_intf_net -intf_net ps8_0_axi_periph_M03_AXI [get_bd_intf_pins axis_signal_gen_v6_5/s_axi] [get_bd_intf_pins ps8_0_axi_periph/M03_AXI]
  connect_bd_intf_net -intf_net ps8_0_axi_periph_M05_AXI [get_bd_intf_pins axis_switch_avg/S_AXI_CTRL] [get_bd_intf_pins ps8_0_axi_periph/M05_AXI]
  connect_bd_intf_net -intf_net ps8_0_axi_periph_M06_AXI [get_bd_intf_pins axis_switch_buf/S_AXI_CTRL] [get_bd_intf_pins ps8_0_axi_periph/M06_AXI]
  connect_bd_intf_net -intf_net ps8_0_axi_periph_M07_AXI [get_bd_intf_pins axis_switch_gen/S_AXI_CTRL] [get_bd_intf_pins ps8_0_axi_periph/M07_AXI]
  connect_bd_intf_net -intf_net ps8_0_axi_periph_M08_AXI [get_bd_intf_pins axis_pfb_readout_v2_0/s_axi] [get_bd_intf_pins ps8_0_axi_periph/M08_AXI]
  connect_bd_intf_net -intf_net ps8_0_axi_periph_M12_AXI [get_bd_intf_pins axis_tproc64x32_x8_0/s_axi] [get_bd_intf_pins ps8_0_axi_periph/M12_AXI]
  connect_bd_intf_net -intf_net ps8_0_axi_periph_M13_AXI [get_bd_intf_pins ps8_0_axi_periph/M13_AXI] [get_bd_intf_pins usp_rf_data_converter_0/s_axi]
  connect_bd_intf_net -intf_net sysref_in_1 [get_bd_intf_ports sysref_in] [get_bd_intf_pins usp_rf_data_converter_0/sysref_in]
  connect_bd_intf_net -intf_net usp_rf_data_converter_0_m20_axis [get_bd_intf_pins axis_pfb_readout_v2_0/s_axis] [get_bd_intf_pins usp_rf_data_converter_0/m20_axis]
  connect_bd_intf_net -intf_net usp_rf_data_converter_0_vout00 [get_bd_intf_ports vout00] [get_bd_intf_pins usp_rf_data_converter_0/vout00]
  connect_bd_intf_net -intf_net usp_rf_data_converter_0_vout10 [get_bd_intf_ports vout10] [get_bd_intf_pins usp_rf_data_converter_0/vout10]
  connect_bd_intf_net -intf_net usp_rf_data_converter_0_vout11 [get_bd_intf_ports vout11] [get_bd_intf_pins usp_rf_data_converter_0/vout11]
  connect_bd_intf_net -intf_net usp_rf_data_converter_0_vout12 [get_bd_intf_ports vout12] [get_bd_intf_pins usp_rf_data_converter_0/vout12]
  connect_bd_intf_net -intf_net usp_rf_data_converter_0_vout13 [get_bd_intf_ports vout13] [get_bd_intf_pins usp_rf_data_converter_0/vout13]
  connect_bd_intf_net -intf_net usp_rf_data_converter_0_vout20 [get_bd_intf_ports vout20] [get_bd_intf_pins usp_rf_data_converter_0/vout20]
  connect_bd_intf_net -intf_net usp_rf_data_converter_0_vout21 [get_bd_intf_ports vout21] [get_bd_intf_pins usp_rf_data_converter_0/vout21]
  connect_bd_intf_net -intf_net usp_rf_data_converter_0_vout22 [get_bd_intf_ports vout22] [get_bd_intf_pins usp_rf_data_converter_0/vout22]
  connect_bd_intf_net -intf_net usp_rf_data_converter_0_vout23 [get_bd_intf_ports vout23] [get_bd_intf_pins usp_rf_data_converter_0/vout23]
  connect_bd_intf_net -intf_net usp_rf_data_converter_0_vout30 [get_bd_intf_ports vout30] [get_bd_intf_pins usp_rf_data_converter_0/vout30]
  connect_bd_intf_net -intf_net usp_rf_data_converter_0_vout31 [get_bd_intf_ports vout31] [get_bd_intf_pins usp_rf_data_converter_0/vout31]
  connect_bd_intf_net -intf_net vin20_1 [get_bd_intf_ports vin20] [get_bd_intf_pins usp_rf_data_converter_0/vin20]
  connect_bd_intf_net -intf_net zynq_ultra_ps_e_0_M_AXI_HPM0_FPD [get_bd_intf_pins axi_smc/S00_AXI] [get_bd_intf_pins zynq_ultra_ps_e_0/M_AXI_HPM0_FPD]
  connect_bd_intf_net -intf_net zynq_ultra_ps_e_0_M_AXI_HPM1_FPD [get_bd_intf_pins ps8_0_axi_periph/S00_AXI] [get_bd_intf_pins zynq_ultra_ps_e_0/M_AXI_HPM1_FPD]

  # Create port connections
  connect_bd_net -net PMOD1_0_LS_1 [get_bd_ports PMOD1_0_LS] [get_bd_pins axis_tproc64x32_x8_0/start]
  connect_bd_net -net axi_bram_ctrl_0_bram_doutb [get_bd_pins axi_bram_ctrl_0_bram/doutb] [get_bd_pins axis_tproc64x32_x8_0/pmem_do]
  connect_bd_net -net axis_set_reg_0_dout [get_bd_pins axis_set_reg_0/dout] [get_bd_pins vect2bits_9_0/din]
  connect_bd_net -net axis_tproc64x32_x8_0_pmem_addr [get_bd_pins axi_bram_ctrl_0_bram/addrb] [get_bd_pins axis_tproc64x32_x8_0/pmem_addr]
  connect_bd_net -net clk_tproc_clk_out1 [get_bd_pins axi_bram_ctrl_0_bram/clkb] [get_bd_pins axis_cc_avg_0/m_axis_aclk] [get_bd_pins axis_cc_avg_1/m_axis_aclk] [get_bd_pins axis_cc_avg_2/m_axis_aclk] [get_bd_pins axis_cc_avg_3/m_axis_aclk] [get_bd_pins axis_cc_sg_0/s_axis_aclk] [get_bd_pins axis_cc_sg_1/s_axis_aclk] [get_bd_pins axis_cc_sg_2/s_axis_aclk] [get_bd_pins axis_cc_sg_3/s_axis_aclk] [get_bd_pins axis_cc_sg_4/s_axis_aclk] [get_bd_pins axis_cc_sg_5/s_axis_aclk] [get_bd_pins axis_cc_sg_6/s_axis_aclk] [get_bd_pins axis_set_reg_0/s_axis_aclk] [get_bd_pins axis_tproc64x32_x8_0/aclk] [get_bd_pins clk_tproc/clk_out1] [get_bd_pins rst_tproc/slowest_sync_clk]
  connect_bd_net -net clk_tproc_locked [get_bd_pins clk_tproc/locked] [get_bd_pins rst_tproc/dcm_locked]
  connect_bd_net -net rst_100_peripheral_aresetn [get_bd_pins axi_bram_ctrl_0/s_axi_aresetn] [get_bd_pins axi_dma_avg/axi_resetn] [get_bd_pins axi_dma_buf/axi_resetn] [get_bd_pins axi_dma_gen/axi_resetn] [get_bd_pins axi_dma_tproc/axi_resetn] [get_bd_pins axi_smc/aresetn] [get_bd_pins axi_smc_1/aresetn] [get_bd_pins axi_smc_2/aresetn] [get_bd_pins axis_avg_buffer_0/m_axis_aresetn] [get_bd_pins axis_avg_buffer_0/s_axi_aresetn] [get_bd_pins axis_avg_buffer_1/m_axis_aresetn] [get_bd_pins axis_avg_buffer_1/s_axi_aresetn] [get_bd_pins axis_avg_buffer_2/m_axis_aresetn] [get_bd_pins axis_avg_buffer_2/s_axi_aresetn] [get_bd_pins axis_avg_buffer_3/m_axis_aresetn] [get_bd_pins axis_avg_buffer_3/s_axi_aresetn] [get_bd_pins axis_cc_avg_0/s_axis_aresetn] [get_bd_pins axis_cc_avg_1/s_axis_aresetn] [get_bd_pins axis_cc_avg_2/s_axis_aresetn] [get_bd_pins axis_cc_avg_3/s_axis_aresetn] [get_bd_pins axis_constant_iq_0/s_axi_aresetn] [get_bd_pins axis_constant_iq_1/s_axi_aresetn] [get_bd_pins axis_constant_iq_2/s_axi_aresetn] [get_bd_pins axis_constant_iq_3/s_axi_aresetn] [get_bd_pins axis_pfb_readout_v2_0/s_axi_aresetn] [get_bd_pins axis_sg_int4_v1_0/s0_axis_aresetn] [get_bd_pins axis_sg_int4_v1_0/s_axi_aresetn] [get_bd_pins axis_sg_int4_v1_1/s0_axis_aresetn] [get_bd_pins axis_sg_int4_v1_1/s_axi_aresetn] [get_bd_pins axis_sg_int4_v1_2/s0_axis_aresetn] [get_bd_pins axis_sg_int4_v1_2/s_axi_aresetn] [get_bd_pins axis_sg_int4_v1_3/s0_axis_aresetn] [get_bd_pins axis_sg_int4_v1_3/s_axi_aresetn] [get_bd_pins axis_sg_mux4_v2_6/s_axi_aresetn] [get_bd_pins axis_signal_gen_v6_4/s0_axis_aresetn] [get_bd_pins axis_signal_gen_v6_4/s_axi_aresetn] [get_bd_pins axis_signal_gen_v6_5/s0_axis_aresetn] [get_bd_pins axis_signal_gen_v6_5/s_axi_aresetn] [get_bd_pins axis_switch_avg/aresetn] [get_bd_pins axis_switch_avg/s_axi_ctrl_aresetn] [get_bd_pins axis_switch_buf/aresetn] [get_bd_pins axis_switch_buf/s_axi_ctrl_aresetn] [get_bd_pins axis_switch_gen/aresetn] [get_bd_pins axis_switch_gen/s_axi_ctrl_aresetn] [get_bd_pins axis_tproc64x32_x8_0/m0_axis_aresetn] [get_bd_pins axis_tproc64x32_x8_0/s0_axis_aresetn] [get_bd_pins axis_tproc64x32_x8_0/s_axi_aresetn] [get_bd_pins ps8_0_axi_periph/ARESETN] [get_bd_pins ps8_0_axi_periph/M00_ARESETN] [get_bd_pins ps8_0_axi_periph/M01_ARESETN] [get_bd_pins ps8_0_axi_periph/M02_ARESETN] [get_bd_pins ps8_0_axi_periph/M03_ARESETN] [get_bd_pins ps8_0_axi_periph/M04_ARESETN] [get_bd_pins ps8_0_axi_periph/M05_ARESETN] [get_bd_pins ps8_0_axi_periph/M06_ARESETN] [get_bd_pins ps8_0_axi_periph/M07_ARESETN] [get_bd_pins ps8_0_axi_periph/M08_ARESETN] [get_bd_pins ps8_0_axi_periph/M09_ARESETN] [get_bd_pins ps8_0_axi_periph/M10_ARESETN] [get_bd_pins ps8_0_axi_periph/M11_ARESETN] [get_bd_pins ps8_0_axi_periph/M12_ARESETN] [get_bd_pins ps8_0_axi_periph/M13_ARESETN] [get_bd_pins ps8_0_axi_periph/S00_ARESETN] [get_bd_pins rst_100/peripheral_aresetn] [get_bd_pins usp_rf_data_converter_0/s_axi_aresetn]
  connect_bd_net -net rst_100_peripheral_reset [get_bd_pins clk_tproc/reset] [get_bd_pins rst_100/peripheral_reset]
  connect_bd_net -net rst_adc2_peripheral_aresetn [get_bd_pins axis_avg_buffer_0/s_axis_aresetn] [get_bd_pins axis_avg_buffer_1/s_axis_aresetn] [get_bd_pins axis_avg_buffer_2/s_axis_aresetn] [get_bd_pins axis_avg_buffer_3/s_axis_aresetn] [get_bd_pins axis_pfb_readout_v2_0/aresetn] [get_bd_pins rst_adc2/peripheral_aresetn] [get_bd_pins usp_rf_data_converter_0/m2_axis_aresetn]
  connect_bd_net -net rst_dac0_peripheral_aresetn [get_bd_pins axis_cc_sg_6/m_axis_aresetn] [get_bd_pins axis_sg_mux4_v2_6/aresetn] [get_bd_pins rst_dac0/peripheral_aresetn] [get_bd_pins usp_rf_data_converter_0/s0_axis_aresetn]
  connect_bd_net -net rst_dac1_peripheral_aresetn [get_bd_pins axis_constant_iq_0/m_axis_aresetn] [get_bd_pins axis_constant_iq_1/m_axis_aresetn] [get_bd_pins axis_constant_iq_2/m_axis_aresetn] [get_bd_pins axis_constant_iq_3/m_axis_aresetn] [get_bd_pins rst_dac1/peripheral_aresetn] [get_bd_pins usp_rf_data_converter_0/s1_axis_aresetn]
  connect_bd_net -net rst_dac2_peripheral_aresetn [get_bd_pins axis_cc_sg_0/m_axis_aresetn] [get_bd_pins axis_cc_sg_1/m_axis_aresetn] [get_bd_pins axis_cc_sg_2/m_axis_aresetn] [get_bd_pins axis_cc_sg_3/m_axis_aresetn] [get_bd_pins axis_sg_int4_v1_0/aresetn] [get_bd_pins axis_sg_int4_v1_1/aresetn] [get_bd_pins axis_sg_int4_v1_2/aresetn] [get_bd_pins axis_sg_int4_v1_3/aresetn] [get_bd_pins rst_dac2/peripheral_aresetn] [get_bd_pins usp_rf_data_converter_0/s2_axis_aresetn]
  connect_bd_net -net rst_dac3_peripheral_aresetn [get_bd_pins axis_cc_sg_4/m_axis_aresetn] [get_bd_pins axis_cc_sg_5/m_axis_aresetn] [get_bd_pins axis_register_slice_0/aresetn] [get_bd_pins axis_register_slice_1/aresetn] [get_bd_pins axis_signal_gen_v6_4/aresetn] [get_bd_pins axis_signal_gen_v6_5/aresetn] [get_bd_pins rst_dac3/peripheral_aresetn] [get_bd_pins usp_rf_data_converter_0/s3_axis_aresetn]
  connect_bd_net -net rst_tproc_peripheral_aresetn [get_bd_pins axis_cc_avg_0/m_axis_aresetn] [get_bd_pins axis_cc_avg_1/m_axis_aresetn] [get_bd_pins axis_cc_avg_2/m_axis_aresetn] [get_bd_pins axis_cc_avg_3/m_axis_aresetn] [get_bd_pins axis_cc_sg_0/s_axis_aresetn] [get_bd_pins axis_cc_sg_1/s_axis_aresetn] [get_bd_pins axis_cc_sg_2/s_axis_aresetn] [get_bd_pins axis_cc_sg_3/s_axis_aresetn] [get_bd_pins axis_cc_sg_4/s_axis_aresetn] [get_bd_pins axis_cc_sg_5/s_axis_aresetn] [get_bd_pins axis_cc_sg_6/s_axis_aresetn] [get_bd_pins axis_set_reg_0/s_axis_aresetn] [get_bd_pins axis_tproc64x32_x8_0/aresetn] [get_bd_pins rst_tproc/peripheral_aresetn]
  connect_bd_net -net usp_rf_data_converter_0_clk_adc2 [get_bd_pins axis_avg_buffer_0/s_axis_aclk] [get_bd_pins axis_avg_buffer_1/s_axis_aclk] [get_bd_pins axis_avg_buffer_2/s_axis_aclk] [get_bd_pins axis_avg_buffer_3/s_axis_aclk] [get_bd_pins axis_pfb_readout_v2_0/aclk] [get_bd_pins rst_adc2/slowest_sync_clk] [get_bd_pins usp_rf_data_converter_0/clk_adc2] [get_bd_pins usp_rf_data_converter_0/m2_axis_aclk]
  connect_bd_net -net usp_rf_data_converter_0_clk_dac0 [get_bd_pins axis_cc_sg_6/m_axis_aclk] [get_bd_pins axis_sg_mux4_v2_6/aclk] [get_bd_pins rst_dac0/slowest_sync_clk] [get_bd_pins usp_rf_data_converter_0/clk_dac0] [get_bd_pins usp_rf_data_converter_0/s0_axis_aclk]
  connect_bd_net -net usp_rf_data_converter_0_clk_dac1 [get_bd_pins axis_constant_iq_0/m_axis_aclk] [get_bd_pins axis_constant_iq_1/m_axis_aclk] [get_bd_pins axis_constant_iq_2/m_axis_aclk] [get_bd_pins axis_constant_iq_3/m_axis_aclk] [get_bd_pins rst_dac1/slowest_sync_clk] [get_bd_pins usp_rf_data_converter_0/clk_dac1] [get_bd_pins usp_rf_data_converter_0/s1_axis_aclk]
  connect_bd_net -net usp_rf_data_converter_0_clk_dac2 [get_bd_pins axis_cc_sg_0/m_axis_aclk] [get_bd_pins axis_cc_sg_1/m_axis_aclk] [get_bd_pins axis_cc_sg_2/m_axis_aclk] [get_bd_pins axis_cc_sg_3/m_axis_aclk] [get_bd_pins axis_sg_int4_v1_0/aclk] [get_bd_pins axis_sg_int4_v1_1/aclk] [get_bd_pins axis_sg_int4_v1_2/aclk] [get_bd_pins axis_sg_int4_v1_3/aclk] [get_bd_pins rst_dac2/slowest_sync_clk] [get_bd_pins usp_rf_data_converter_0/clk_dac2] [get_bd_pins usp_rf_data_converter_0/s2_axis_aclk]
  connect_bd_net -net usp_rf_data_converter_0_clk_dac3 [get_bd_pins axis_cc_sg_4/m_axis_aclk] [get_bd_pins axis_cc_sg_5/m_axis_aclk] [get_bd_pins axis_register_slice_0/aclk] [get_bd_pins axis_register_slice_1/aclk] [get_bd_pins axis_signal_gen_v6_4/aclk] [get_bd_pins axis_signal_gen_v6_5/aclk] [get_bd_pins rst_dac3/slowest_sync_clk] [get_bd_pins usp_rf_data_converter_0/clk_dac3] [get_bd_pins usp_rf_data_converter_0/s3_axis_aclk]
  connect_bd_net -net vect2bits_9_0_dout0 [get_bd_ports PMOD0_0_LS] [get_bd_pins vect2bits_9_0/dout0]
  connect_bd_net -net vect2bits_9_0_dout1 [get_bd_ports PMOD0_1_LS] [get_bd_pins vect2bits_9_0/dout1]
  connect_bd_net -net vect2bits_9_0_dout2 [get_bd_ports PMOD0_2_LS] [get_bd_pins vect2bits_9_0/dout2]
  connect_bd_net -net vect2bits_9_0_dout3 [get_bd_ports PMOD0_3_LS] [get_bd_pins vect2bits_9_0/dout3]
  connect_bd_net -net vect2bits_9_0_dout4 [get_bd_pins axis_avg_buffer_0/trigger] [get_bd_pins vect2bits_9_0/dout4]
  connect_bd_net -net vect2bits_9_0_dout5 [get_bd_pins axis_avg_buffer_1/trigger] [get_bd_pins vect2bits_9_0/dout5]
  connect_bd_net -net vect2bits_9_0_dout6 [get_bd_pins axis_avg_buffer_2/trigger] [get_bd_pins vect2bits_9_0/dout6]
  connect_bd_net -net vect2bits_9_0_dout7 [get_bd_pins axis_avg_buffer_3/trigger] [get_bd_pins vect2bits_9_0/dout7]
  connect_bd_net -net xlconstant_0_dout [get_bd_pins axi_bram_ctrl_0_bram/dinb] [get_bd_pins xlconstant_0/dout]
  connect_bd_net -net xlconstant_1_dout [get_bd_pins axi_bram_ctrl_0_bram/enb] [get_bd_pins xlconstant_1/dout]
  connect_bd_net -net xlconstant_2_dout [get_bd_pins axi_bram_ctrl_0_bram/rstb] [get_bd_pins xlconstant_2/dout]
  connect_bd_net -net xlconstant_3_dout [get_bd_pins axi_bram_ctrl_0_bram/web] [get_bd_pins xlconstant_3/dout]
  connect_bd_net -net zynq_ultra_ps_e_0_pl_clk0 [get_bd_pins axi_bram_ctrl_0/s_axi_aclk] [get_bd_pins axi_dma_avg/m_axi_s2mm_aclk] [get_bd_pins axi_dma_avg/s_axi_lite_aclk] [get_bd_pins axi_dma_buf/m_axi_s2mm_aclk] [get_bd_pins axi_dma_buf/s_axi_lite_aclk] [get_bd_pins axi_dma_gen/m_axi_mm2s_aclk] [get_bd_pins axi_dma_gen/s_axi_lite_aclk] [get_bd_pins axi_dma_tproc/m_axi_mm2s_aclk] [get_bd_pins axi_dma_tproc/m_axi_s2mm_aclk] [get_bd_pins axi_dma_tproc/s_axi_lite_aclk] [get_bd_pins axi_smc/aclk] [get_bd_pins axi_smc_1/aclk] [get_bd_pins axi_smc_2/aclk] [get_bd_pins axis_avg_buffer_0/m_axis_aclk] [get_bd_pins axis_avg_buffer_0/s_axi_aclk] [get_bd_pins axis_avg_buffer_1/m_axis_aclk] [get_bd_pins axis_avg_buffer_1/s_axi_aclk] [get_bd_pins axis_avg_buffer_2/m_axis_aclk] [get_bd_pins axis_avg_buffer_2/s_axi_aclk] [get_bd_pins axis_avg_buffer_3/m_axis_aclk] [get_bd_pins axis_avg_buffer_3/s_axi_aclk] [get_bd_pins axis_cc_avg_0/s_axis_aclk] [get_bd_pins axis_cc_avg_1/s_axis_aclk] [get_bd_pins axis_cc_avg_2/s_axis_aclk] [get_bd_pins axis_cc_avg_3/s_axis_aclk] [get_bd_pins axis_constant_iq_0/s_axi_aclk] [get_bd_pins axis_constant_iq_1/s_axi_aclk] [get_bd_pins axis_constant_iq_2/s_axi_aclk] [get_bd_pins axis_constant_iq_3/s_axi_aclk] [get_bd_pins axis_pfb_readout_v2_0/s_axi_aclk] [get_bd_pins axis_sg_int4_v1_0/s0_axis_aclk] [get_bd_pins axis_sg_int4_v1_0/s_axi_aclk] [get_bd_pins axis_sg_int4_v1_1/s0_axis_aclk] [get_bd_pins axis_sg_int4_v1_1/s_axi_aclk] [get_bd_pins axis_sg_int4_v1_2/s0_axis_aclk] [get_bd_pins axis_sg_int4_v1_2/s_axi_aclk] [get_bd_pins axis_sg_int4_v1_3/s0_axis_aclk] [get_bd_pins axis_sg_int4_v1_3/s_axi_aclk] [get_bd_pins axis_sg_mux4_v2_6/s_axi_aclk] [get_bd_pins axis_signal_gen_v6_4/s0_axis_aclk] [get_bd_pins axis_signal_gen_v6_4/s_axi_aclk] [get_bd_pins axis_signal_gen_v6_5/s0_axis_aclk] [get_bd_pins axis_signal_gen_v6_5/s_axi_aclk] [get_bd_pins axis_switch_avg/aclk] [get_bd_pins axis_switch_avg/s_axi_ctrl_aclk] [get_bd_pins axis_switch_buf/aclk] [get_bd_pins axis_switch_buf/s_axi_ctrl_aclk] [get_bd_pins axis_switch_gen/aclk] [get_bd_pins axis_switch_gen/s_axi_ctrl_aclk] [get_bd_pins axis_tproc64x32_x8_0/m0_axis_aclk] [get_bd_pins axis_tproc64x32_x8_0/s0_axis_aclk] [get_bd_pins axis_tproc64x32_x8_0/s_axi_aclk] [get_bd_pins clk_tproc/clk_in1] [get_bd_pins ps8_0_axi_periph/ACLK] [get_bd_pins ps8_0_axi_periph/M00_ACLK] [get_bd_pins ps8_0_axi_periph/M01_ACLK] [get_bd_pins ps8_0_axi_periph/M02_ACLK] [get_bd_pins ps8_0_axi_periph/M03_ACLK] [get_bd_pins ps8_0_axi_periph/M04_ACLK] [get_bd_pins ps8_0_axi_periph/M05_ACLK] [get_bd_pins ps8_0_axi_periph/M06_ACLK] [get_bd_pins ps8_0_axi_periph/M07_ACLK] [get_bd_pins ps8_0_axi_periph/M08_ACLK] [get_bd_pins ps8_0_axi_periph/M09_ACLK] [get_bd_pins ps8_0_axi_periph/M10_ACLK] [get_bd_pins ps8_0_axi_periph/M11_ACLK] [get_bd_pins ps8_0_axi_periph/M12_ACLK] [get_bd_pins ps8_0_axi_periph/M13_ACLK] [get_bd_pins ps8_0_axi_periph/S00_ACLK] [get_bd_pins rst_100/slowest_sync_clk] [get_bd_pins usp_rf_data_converter_0/s_axi_aclk] [get_bd_pins zynq_ultra_ps_e_0/maxihpm0_fpd_aclk] [get_bd_pins zynq_ultra_ps_e_0/maxihpm1_fpd_aclk] [get_bd_pins zynq_ultra_ps_e_0/pl_clk0] [get_bd_pins zynq_ultra_ps_e_0/saxihpc0_fpd_aclk] [get_bd_pins zynq_ultra_ps_e_0/saxihpc1_fpd_aclk]
  connect_bd_net -net zynq_ultra_ps_e_0_pl_resetn0 [get_bd_pins rst_100/ext_reset_in] [get_bd_pins rst_adc2/ext_reset_in] [get_bd_pins rst_dac0/ext_reset_in] [get_bd_pins rst_dac1/ext_reset_in] [get_bd_pins rst_dac2/ext_reset_in] [get_bd_pins rst_dac3/ext_reset_in] [get_bd_pins rst_tproc/ext_reset_in] [get_bd_pins zynq_ultra_ps_e_0/pl_resetn0]

  # Create address segments
  assign_bd_address -offset 0x00000000 -range 0x80000000 -target_address_space [get_bd_addr_spaces axi_dma_avg/Data_S2MM] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP0/HPC0_DDR_LOW] -force
  assign_bd_address -offset 0xC0000000 -range 0x20000000 -target_address_space [get_bd_addr_spaces axi_dma_avg/Data_S2MM] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP0/HPC0_QSPI] -force
  assign_bd_address -offset 0x00000000 -range 0x80000000 -target_address_space [get_bd_addr_spaces axi_dma_buf/Data_S2MM] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP0/HPC0_DDR_LOW] -force
  assign_bd_address -offset 0xC0000000 -range 0x20000000 -target_address_space [get_bd_addr_spaces axi_dma_buf/Data_S2MM] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP0/HPC0_QSPI] -force
  assign_bd_address -offset 0x00000000 -range 0x80000000 -target_address_space [get_bd_addr_spaces axi_dma_gen/Data_MM2S] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP0/HPC0_DDR_LOW] -force
  assign_bd_address -offset 0xC0000000 -range 0x20000000 -target_address_space [get_bd_addr_spaces axi_dma_gen/Data_MM2S] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP0/HPC0_QSPI] -force
  assign_bd_address -offset 0x00000000 -range 0x80000000 -target_address_space [get_bd_addr_spaces axi_dma_tproc/Data_MM2S] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP1/HPC1_DDR_LOW] -force
  assign_bd_address -offset 0x00000000 -range 0x80000000 -target_address_space [get_bd_addr_spaces axi_dma_tproc/Data_S2MM] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP1/HPC1_DDR_LOW] -force
  assign_bd_address -offset 0xC0000000 -range 0x20000000 -target_address_space [get_bd_addr_spaces axi_dma_tproc/Data_MM2S] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP1/HPC1_QSPI] -force
  assign_bd_address -offset 0xC0000000 -range 0x20000000 -target_address_space [get_bd_addr_spaces axi_dma_tproc/Data_S2MM] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP1/HPC1_QSPI] -force
  assign_bd_address -offset 0xA0040000 -range 0x00002000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axi_bram_ctrl_0/S_AXI/Mem0] -force
  assign_bd_address -offset 0xA0000000 -range 0x00010000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axi_dma_avg/S_AXI_LITE/Reg] -force
  assign_bd_address -offset 0xA0010000 -range 0x00010000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axi_dma_buf/S_AXI_LITE/Reg] -force
  assign_bd_address -offset 0xA0020000 -range 0x00010000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axi_dma_gen/S_AXI_LITE/Reg] -force
  assign_bd_address -offset 0xA0030000 -range 0x00010000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axi_dma_tproc/S_AXI_LITE/Reg] -force
  assign_bd_address -offset 0xA0050000 -range 0x00010000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axis_avg_buffer_0/s_axi/reg0] -force
  assign_bd_address -offset 0xA0060000 -range 0x00010000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axis_avg_buffer_1/s_axi/reg0] -force
  assign_bd_address -offset 0xA0070000 -range 0x00010000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axis_avg_buffer_2/s_axi/reg0] -force
  assign_bd_address -offset 0xA0080000 -range 0x00010000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axis_avg_buffer_3/s_axi/reg0] -force
  assign_bd_address -offset 0xA0090000 -range 0x00000400 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axis_constant_iq_0/s_axi/reg0] -force
  assign_bd_address -offset 0xA00A0000 -range 0x00000400 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axis_constant_iq_1/s_axi/reg0] -force
  assign_bd_address -offset 0xA00B0000 -range 0x00000400 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axis_constant_iq_2/s_axi/reg0] -force
  assign_bd_address -offset 0xA00C0000 -range 0x00000400 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axis_constant_iq_3/s_axi/reg0] -force
  assign_bd_address -offset 0xB0080000 -range 0x00010000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axis_pfb_readout_v2_0/s_axi/reg0] -force
  assign_bd_address -offset 0xA00E0000 -range 0x00000400 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axis_sg_int4_v1_0/s_axi/reg0] -force
  assign_bd_address -offset 0xA00F0000 -range 0x00000400 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axis_sg_int4_v1_1/s_axi/reg0] -force
  assign_bd_address -offset 0xB0000000 -range 0x00010000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axis_sg_int4_v1_2/s_axi/reg0] -force
  assign_bd_address -offset 0xB0010000 -range 0x00010000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axis_sg_int4_v1_3/s_axi/reg0] -force
  assign_bd_address -offset 0xA00D0000 -range 0x00010000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axis_sg_mux4_v2_6/s_axi/reg0] -force
  assign_bd_address -offset 0xB0020000 -range 0x00010000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axis_signal_gen_v6_4/s_axi/reg0] -force
  assign_bd_address -offset 0xB0030000 -range 0x00010000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axis_signal_gen_v6_5/s_axi/reg0] -force
  assign_bd_address -offset 0xB0050000 -range 0x00010000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axis_switch_avg/S_AXI_CTRL/Reg] -force
  assign_bd_address -offset 0xB0060000 -range 0x00010000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axis_switch_buf/S_AXI_CTRL/Reg] -force
  assign_bd_address -offset 0xB0070000 -range 0x00010000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axis_switch_gen/S_AXI_CTRL/Reg] -force
  assign_bd_address -offset 0x000500000000 -range 0x000100000000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs axis_tproc64x32_x8_0/s_axi/reg0] -force
  assign_bd_address -offset 0xB00C0000 -range 0x00040000 -target_address_space [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] [get_bd_addr_segs usp_rf_data_converter_0/s_axi/Reg] -force

  # Exclude Address Segments
  exclude_bd_addr_seg -offset 0x000800000000 -range 0x000100000000 -target_address_space [get_bd_addr_spaces axi_dma_avg/Data_S2MM] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP0/HPC0_DDR_HIGH]
  exclude_bd_addr_seg -offset 0xFF000000 -range 0x01000000 -target_address_space [get_bd_addr_spaces axi_dma_avg/Data_S2MM] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP0/HPC0_LPS_OCM]
  exclude_bd_addr_seg -offset 0x000800000000 -range 0x000100000000 -target_address_space [get_bd_addr_spaces axi_dma_buf/Data_S2MM] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP0/HPC0_DDR_HIGH]
  exclude_bd_addr_seg -offset 0xFF000000 -range 0x01000000 -target_address_space [get_bd_addr_spaces axi_dma_buf/Data_S2MM] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP0/HPC0_LPS_OCM]
  exclude_bd_addr_seg -offset 0x000800000000 -range 0x000100000000 -target_address_space [get_bd_addr_spaces axi_dma_gen/Data_MM2S] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP0/HPC0_DDR_HIGH]
  exclude_bd_addr_seg -offset 0xFF000000 -range 0x01000000 -target_address_space [get_bd_addr_spaces axi_dma_gen/Data_MM2S] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP0/HPC0_LPS_OCM]
  exclude_bd_addr_seg -offset 0x000800000000 -range 0x000100000000 -target_address_space [get_bd_addr_spaces axi_dma_tproc/Data_MM2S] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP1/HPC1_DDR_HIGH]
  exclude_bd_addr_seg -offset 0xFF000000 -range 0x01000000 -target_address_space [get_bd_addr_spaces axi_dma_tproc/Data_MM2S] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP1/HPC1_LPS_OCM]
  exclude_bd_addr_seg -offset 0x000800000000 -range 0x000100000000 -target_address_space [get_bd_addr_spaces axi_dma_tproc/Data_S2MM] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP1/HPC1_DDR_HIGH]
  exclude_bd_addr_seg -offset 0xFF000000 -range 0x01000000 -target_address_space [get_bd_addr_spaces axi_dma_tproc/Data_S2MM] [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP1/HPC1_LPS_OCM]

  # Perform GUI Layout
  regenerate_bd_layout -layout_string {
   "ActiveEmotionalView":"Default View",
   "Default View_ScaleFactor":"0.0820408",
   "Default View_TopLeft":"-4839,-3730",
   "ExpandedHierarchyInLayout":"",
   "guistr":"# # String gsaved with Nlview 7.0r4  2019-12-20 bk=1.5203 VDI=41 GEI=36 GUI=JA:10.0 TLS
#  -string -flagsOSRD
preplace port adc2_clk -pg 1 -lvl 11 -x 5000 -y 2070 -defaultsOSRD -right
preplace port dac2_clk -pg 1 -lvl 11 -x 5000 -y 2050 -defaultsOSRD -right
preplace port sysref_in -pg 1 -lvl 11 -x 5000 -y 2030 -defaultsOSRD -right
preplace port vin20 -pg 1 -lvl 11 -x 5000 -y 2010 -defaultsOSRD -right
preplace port vout00 -pg 1 -lvl 11 -x 5000 -y 2260 -defaultsOSRD
preplace port vout10 -pg 1 -lvl 11 -x 5000 -y 2280 -defaultsOSRD
preplace port vout11 -pg 1 -lvl 11 -x 5000 -y 2300 -defaultsOSRD
preplace port vout12 -pg 1 -lvl 11 -x 5000 -y 2320 -defaultsOSRD
preplace port vout13 -pg 1 -lvl 11 -x 5000 -y 2340 -defaultsOSRD
preplace port vout20 -pg 1 -lvl 11 -x 5000 -y 2360 -defaultsOSRD
preplace port vout21 -pg 1 -lvl 11 -x 5000 -y 2380 -defaultsOSRD
preplace port vout22 -pg 1 -lvl 11 -x 5000 -y 2400 -defaultsOSRD
preplace port vout23 -pg 1 -lvl 11 -x 5000 -y 2420 -defaultsOSRD
preplace port vout30 -pg 1 -lvl 11 -x 5000 -y 2440 -defaultsOSRD
preplace port vout31 -pg 1 -lvl 11 -x 5000 -y 2460 -defaultsOSRD
preplace port PMOD0_0_LS -pg 1 -lvl 11 -x 5000 -y 3320 -defaultsOSRD
preplace port PMOD0_1_LS -pg 1 -lvl 11 -x 5000 -y 3340 -defaultsOSRD
preplace port PMOD0_2_LS -pg 1 -lvl 11 -x 5000 -y 3360 -defaultsOSRD
preplace port PMOD0_3_LS -pg 1 -lvl 11 -x 5000 -y 3380 -defaultsOSRD
preplace port PMOD1_0_LS -pg 1 -lvl 0 -x -140 -y 680 -defaultsOSRD
preplace inst axi_bram_ctrl_0 -pg 1 -lvl 1 -x 40 -y 1010 -defaultsOSRD
preplace inst axi_bram_ctrl_0_bram -pg 1 -lvl 2 -x 450 -y 1130 -defaultsOSRD
preplace inst axi_dma_avg -pg 1 -lvl 10 -x 4790 -y 1010 -defaultsOSRD
preplace inst axi_dma_buf -pg 1 -lvl 10 -x 4790 -y 1190 -defaultsOSRD -resize 320 156
preplace inst axi_dma_gen -pg 1 -lvl 2 -x 450 -y -320 -defaultsOSRD
preplace inst axi_dma_tproc -pg 1 -lvl 2 -x 450 -y 120 -defaultsOSRD
preplace inst axi_smc -pg 1 -lvl 5 -x 2080 -y -2530 -defaultsOSRD
preplace inst axi_smc_1 -pg 1 -lvl 3 -x 870 -y -3220 -defaultsOSRD
preplace inst axi_smc_2 -pg 1 -lvl 3 -x 870 -y -2880 -defaultsOSRD
preplace inst axis_avg_buffer_0 -pg 1 -lvl 8 -x 3980 -y 330 -defaultsOSRD
preplace inst axis_avg_buffer_1 -pg 1 -lvl 8 -x 3980 -y 600 -defaultsOSRD -resize 220 236
preplace inst axis_avg_buffer_2 -pg 1 -lvl 8 -x 3980 -y 870 -defaultsOSRD -resize 220 236
preplace inst axis_avg_buffer_3 -pg 1 -lvl 8 -x 3980 -y 1150 -defaultsOSRD -resize 220 236
preplace inst axis_cc_avg_0 -pg 1 -lvl 9 -x 4410 -y 100 -defaultsOSRD -resize 220 156
preplace inst axis_cc_avg_1 -pg 1 -lvl 9 -x 4410 -y 280 -defaultsOSRD -resize 220 156
preplace inst axis_cc_avg_2 -pg 1 -lvl 9 -x 4410 -y 460 -defaultsOSRD -resize 220 156
preplace inst axis_cc_avg_3 -pg 1 -lvl 9 -x 4410 -y 640 -defaultsOSRD -resize 220 156
preplace inst axis_cc_sg_0 -pg 1 -lvl 3 -x 870 -y 520 -defaultsOSRD -resize 220 156
preplace inst axis_cc_sg_1 -pg 1 -lvl 3 -x 870 -y 720 -defaultsOSRD -resize 220 156
preplace inst axis_cc_sg_2 -pg 1 -lvl 3 -x 870 -y 900 -defaultsOSRD -resize 220 156
preplace inst axis_cc_sg_3 -pg 1 -lvl 3 -x 870 -y 1100 -defaultsOSRD -resize 220 156
preplace inst axis_cc_sg_4 -pg 1 -lvl 3 -x 870 -y 1370 -defaultsOSRD
preplace inst axis_cc_sg_5 -pg 1 -lvl 3 -x 870 -y 1670 -defaultsOSRD -resize 220 156
preplace inst axis_cc_sg_6 -pg 1 -lvl 3 -x 870 -y 1930 -defaultsOSRD -resize 220 156
preplace inst axis_constant_iq_0 -pg 1 -lvl 6 -x 2670 -y 2150 -defaultsOSRD
preplace inst axis_constant_iq_1 -pg 1 -lvl 6 -x 2670 -y 2340 -defaultsOSRD -resize 220 156
preplace inst axis_constant_iq_2 -pg 1 -lvl 6 -x 2670 -y 2520 -defaultsOSRD -resize 220 156
preplace inst axis_constant_iq_3 -pg 1 -lvl 6 -x 2670 -y 2700 -defaultsOSRD -resize 220 156
preplace inst axis_pfb_readout_v2_0 -pg 1 -lvl 7 -x 3280 -y 390 -defaultsOSRD
preplace inst axis_register_slice_0 -pg 1 -lvl 5 -x 2080 -y 1400 -defaultsOSRD
preplace inst axis_register_slice_1 -pg 1 -lvl 5 -x 2080 -y 1690 -defaultsOSRD -resize 180 116
preplace inst axis_set_reg_0 -pg 1 -lvl 4 -x 1540 -y 3440 -defaultsOSRD
preplace inst axis_sg_int4_v1_0 -pg 1 -lvl 4 -x 1540 -y 190 -defaultsOSRD
preplace inst axis_sg_int4_v1_1 -pg 1 -lvl 4 -x 1540 -y 450 -defaultsOSRD -resize 220 236
preplace inst axis_sg_int4_v1_2 -pg 1 -lvl 4 -x 1540 -y 710 -defaultsOSRD -resize 220 236
preplace inst axis_sg_int4_v1_3 -pg 1 -lvl 4 -x 1540 -y 1050 -defaultsOSRD -resize 220 236
preplace inst axis_signal_gen_v6_4 -pg 1 -lvl 4 -x 1540 -y 1370 -defaultsOSRD
preplace inst axis_signal_gen_v6_5 -pg 1 -lvl 4 -x 1540 -y 1710 -defaultsOSRD
preplace inst axis_switch_avg -pg 1 -lvl 9 -x 4410 -y 910 -defaultsOSRD
preplace inst axis_switch_buf -pg 1 -lvl 9 -x 4410 -y 1190 -defaultsOSRD -resize 240 236
preplace inst axis_switch_gen -pg 1 -lvl 3 -x 870 -y -290 -defaultsOSRD
preplace inst axis_tproc64x32_x8_0 -pg 1 -lvl 2 -x 450 -y 550 -defaultsOSRD
preplace inst clk_tproc -pg 1 -lvl 4 -x 1540 -y -920 -defaultsOSRD
preplace inst ps8_0_axi_periph -pg 1 -lvl 5 -x 2080 -y -3350 -defaultsOSRD
preplace inst rst_100 -pg 1 -lvl 4 -x 1540 -y -2550 -defaultsOSRD
preplace inst rst_adc2 -pg 1 -lvl 4 -x 1540 -y -2160 -defaultsOSRD -resize 320 156
preplace inst rst_dac0 -pg 1 -lvl 4 -x 1540 -y -1960 -defaultsOSRD -resize 320 156
preplace inst rst_dac1 -pg 1 -lvl 4 -x 1540 -y -1750 -defaultsOSRD -resize 320 156
preplace inst rst_dac2 -pg 1 -lvl 4 -x 1540 -y -1570 -defaultsOSRD -resize 320 156
preplace inst rst_dac3 -pg 1 -lvl 4 -x 1540 -y -1360 -defaultsOSRD -resize 320 156
preplace inst rst_tproc -pg 1 -lvl 4 -x 1540 -y -1100 -defaultsOSRD -resize 320 156
preplace inst usp_rf_data_converter_0 -pg 1 -lvl 7 -x 3280 -y 2410 -defaultsOSRD
preplace inst vect2bits_9_0 -pg 1 -lvl 6 -x 2670 -y 3440 -defaultsOSRD
preplace inst xlconstant_0 -pg 1 -lvl 1 -x 40 -y 1130 -defaultsOSRD
preplace inst xlconstant_1 -pg 1 -lvl 1 -x 40 -y 1240 -defaultsOSRD -resize 140 88
preplace inst xlconstant_2 -pg 1 -lvl 1 -x 40 -y 1370 -defaultsOSRD -resize 140 88
preplace inst xlconstant_3 -pg 1 -lvl 1 -x 40 -y 1480 -defaultsOSRD -resize 140 88
preplace inst zynq_ultra_ps_e_0 -pg 1 -lvl 4 -x 1540 -y -2890 -defaultsOSRD
preplace inst axis_sg_mux4_v2_6 -pg 1 -lvl 4 -x 1540 -y 1980 -defaultsOSRD
preplace netloc PMOD1_0_LS_1 1 0 2 N 680 NJ
preplace netloc axi_bram_ctrl_0_bram_doutb 1 1 1 260 700n
preplace netloc axis_set_reg_0_dout 1 4 2 N 3440 N
preplace netloc axis_tproc64x32_x8_0_pmem_addr 1 1 2 270 770 630
preplace netloc clk_tproc_clk_out1 1 1 8 250 780 710 410 1100 -990 1890 -120 2470 -60 N -60 N -60 4260
preplace netloc clk_tproc_locked 1 3 2 1230 -1200 1850
preplace netloc rst_100_peripheral_aresetn 1 0 10 -100 620 190J -220 700J -170 1060J -170 1910 -110 2330 400 3030J 510 3510J 180 4210J 1050 4600J
preplace netloc rst_100_peripheral_reset 1 3 2 1200 -2450 1850
preplace netloc rst_adc2_peripheral_aresetn 1 4 4 NJ -2120 2480 -70 3000 500 3570
preplace netloc rst_dac0_peripheral_aresetn 1 2 5 730 1830 1030 1850 1870 2010 NJ 2010 2810J
preplace netloc rst_dac1_peripheral_aresetn 1 4 3 N -1710 2340 2030 2840J
preplace netloc rst_dac2_peripheral_aresetn 1 2 5 730 420 1180J 40 1900 160 N 160 2900
preplace netloc rst_dac3_peripheral_aresetn 1 2 5 720 1470 1180J 1510 1860 890 2350 1370 2860J
preplace netloc rst_tproc_peripheral_aresetn 1 1 8 270 760 700J 390 1020J 50 1880 170 N 170 N 170 N 170 4270
preplace netloc usp_rf_data_converter_0_clk_adc2 1 3 5 1210 0 NJ 0 2350 150 2980J 260 3470
preplace netloc usp_rf_data_converter_0_clk_dac0 1 2 6 720 1820 1080 2090 NJ 2090 2440J 2040 2830J 2080 3420
preplace netloc usp_rf_data_converter_0_clk_dac1 1 3 5 1190 2100 NJ 2100 2540 2050 2800J 2060 3430
preplace netloc usp_rf_data_converter_0_clk_dac2 1 2 6 720 400 1170 1220 NJ 1220 2310 1390 2850J 2040 3450
preplace netloc usp_rf_data_converter_0_clk_dac3 1 2 6 730 1480 1150 1520 1900J 1610 2240 1990 2820J 2010 3460
preplace netloc vect2bits_9_0_dout0 1 6 5 NJ 3320 NJ 3320 NJ 3320 NJ 3320 N
preplace netloc vect2bits_9_0_dout1 1 6 5 N 3340 NJ 3340 NJ 3340 NJ 3340 NJ
preplace netloc vect2bits_9_0_dout2 1 6 5 N 3360 NJ 3360 NJ 3360 NJ 3360 NJ
preplace netloc vect2bits_9_0_dout3 1 6 5 N 3380 NJ 3380 NJ 3380 NJ 3380 NJ
preplace netloc vect2bits_9_0_dout4 1 6 2 2870 270 3550J
preplace netloc vect2bits_9_0_dout5 1 6 2 2920 600 NJ
preplace netloc vect2bits_9_0_dout6 1 6 2 2950 870 NJ
preplace netloc vect2bits_9_0_dout7 1 6 2 2990 1150 NJ
preplace netloc xlconstant_0_dout 1 1 1 N 1130
preplace netloc xlconstant_1_dout 1 1 1 200 1170n
preplace netloc xlconstant_2_dout 1 1 1 230 1190n
preplace netloc xlconstant_3_dout 1 1 1 260 1210n
preplace netloc zynq_ultra_ps_e_0_pl_clk0 1 0 10 -110 600 180J -230 640J -3020 1090J -3020 1930 -2740 2450 390 3050J 520 3520J 190 4230J 1330 4610J
preplace netloc zynq_ultra_ps_e_0_pl_resetn0 1 3 2 1220 -2660 1850
preplace netloc adc2_clk_1 1 6 5 3100J 2070 N 2070 N 2070 N 2070 N
preplace netloc axi_bram_ctrl_0_BRAM_PORTA 1 1 1 210 1010n
preplace netloc axi_dma_0_M_AXIS_MM2S 1 2 1 660 -340n
preplace netloc axi_dma_avg_M_AXI_S2MM 1 2 9 710 -100 N -100 N -100 2460 -50 N -50 N -50 N -50 N -50 4980
preplace netloc axi_dma_buf_M_AXI_S2MM 1 2 9 720 -90 NJ -90 NJ -90 2440J -40 NJ -40 NJ -40 NJ -40 NJ -40 4970
preplace netloc axi_dma_gen_M_AXI_MM2S 1 2 1 630 -3220n
preplace netloc axi_dma_tproc_M_AXIS_MM2S 1 1 2 260 -10 640
preplace netloc axi_dma_tproc_M_AXI_MM2S 1 2 1 650J -2910n
preplace netloc axi_dma_tproc_M_AXI_S2MM 1 2 1 690 -2890n
preplace netloc axi_smc_1_M00_AXI 1 3 1 1230 -3220n
preplace netloc axi_smc_2_M00_AXI 1 3 1 1080 -2930n
preplace netloc axi_smc_M00_AXI 1 0 6 -120 -80 NJ -80 NJ -80 NJ -80 NJ -80 2260
preplace netloc axi_smc_M01_AXI 1 5 5 2540 -130 NJ -130 NJ -130 NJ -130 4610J
preplace netloc axi_smc_M02_AXI 1 5 5 2530 -120 NJ -120 NJ -120 NJ -120 4590J
preplace netloc axi_smc_M03_AXI 1 1 5 180 -2750 NJ -2750 NJ -2750 NJ -2750 2270
preplace netloc axi_smc_M04_AXI 1 1 5 250 -70 NJ -70 NJ -70 NJ -70 2250
preplace netloc axi_smc_M05_AXI 1 5 3 2520J -110 NJ -110 3570J
preplace netloc axi_smc_M06_AXI 1 5 3 2510J -100 NJ -100 3560J
preplace netloc axi_smc_M07_AXI 1 5 3 2500J -90 NJ -90 3540J
preplace netloc axi_smc_M08_AXI 1 5 3 2490J -80 NJ -80 3500J
preplace netloc axi_smc_M09_AXI 1 5 1 2430 -2500n
preplace netloc axi_smc_M10_AXI 1 5 1 2410 -2480n
preplace netloc axi_smc_M11_AXI 1 5 1 2390 -2460n
preplace netloc axi_smc_M12_AXI 1 5 1 2370 -2440n
preplace netloc axi_smc_M14_AXI 1 3 3 1210 10 NJ 10 2240
preplace netloc axi_smc_M15_AXI 1 3 3 1220 20 NJ 20 2230
preplace netloc axis_avg_buffer_0_m0_axis 1 8 1 4240 310n
preplace netloc axis_avg_buffer_0_m1_axis 1 8 1 4200 330n
preplace netloc axis_avg_buffer_0_m2_axis 1 8 1 4110 60n
preplace netloc axis_avg_buffer_1_m0_axis 1 8 1 4220 580n
preplace netloc axis_avg_buffer_1_m1_axis 1 8 1 4130 600n
preplace netloc axis_avg_buffer_1_m2_axis 1 8 1 4190 240n
preplace netloc axis_avg_buffer_2_m0_axis 1 8 1 4170 850n
preplace netloc axis_avg_buffer_2_m1_axis 1 8 1 4160 870n
preplace netloc axis_avg_buffer_2_m2_axis 1 8 1 4110 420n
preplace netloc axis_avg_buffer_3_m0_axis 1 8 1 4120 890n
preplace netloc axis_avg_buffer_3_m1_axis 1 8 1 4150 1150n
preplace netloc axis_avg_buffer_3_m2_axis 1 8 1 4140 600n
preplace netloc axis_cc_avg_0_M_AXIS 1 1 9 200 -60 NJ -60 NJ -60 NJ -60 2420 -30 NJ -30 NJ -30 NJ -30 4580
preplace netloc axis_cc_avg_1_M_AXIS 1 1 9 210 -50 NJ -50 NJ -50 NJ -50 2400 -20 NJ -20 NJ -20 NJ -20 4570
preplace netloc axis_cc_avg_2_M_AXIS 1 1 9 220 -40 NJ -40 NJ -40 NJ -40 2380 -10 NJ -10 NJ -10 NJ -10 4560
preplace netloc axis_cc_avg_3_M_AXIS 1 1 9 230 -30 NJ -30 NJ -30 NJ -30 2360 0 NJ 0 NJ 0 NJ 0 4550
preplace netloc axis_cc_sg_0_M_AXIS 1 3 1 1040 130n
preplace netloc axis_cc_sg_1_M_AXIS 1 3 1 1070 390n
preplace netloc axis_cc_sg_2_M_AXIS 1 3 1 1110 650n
preplace netloc axis_cc_sg_3_M_AXIS 1 3 1 1120 990n
preplace netloc axis_cc_sg_4_M_AXIS 1 3 1 1040 1310n
preplace netloc axis_cc_sg_5_M_AXIS 1 3 1 1170 1650n
preplace netloc axis_constant_iq_0_m_axis 1 6 1 2880 2150n
preplace netloc axis_constant_iq_1_m_axis 1 6 1 2910 2200n
preplace netloc axis_constant_iq_2_m_axis 1 6 1 2940 2220n
preplace netloc axis_constant_iq_3_m_axis 1 6 1 2960 2240n
preplace netloc axis_pfb_readout_v2_0_m0_axis 1 7 1 3530 250n
preplace netloc axis_pfb_readout_v2_0_m1_axis 1 7 1 3530 380n
preplace netloc axis_pfb_readout_v2_0_m2_axis 1 7 1 3490 400n
preplace netloc axis_pfb_readout_v2_0_m3_axis 1 7 1 3480 420n
preplace netloc axis_register_slice_0_m_axis 1 5 2 NJ 1400 2930
preplace netloc axis_register_slice_1_m_axis 1 5 2 2230 2000 2890J
preplace netloc axis_sg_int4_v1_0_m_axis 1 4 3 N 190 N 190 3040
preplace netloc axis_sg_int4_v1_1_m_axis 1 4 3 N 450 N 450 3020
preplace netloc axis_sg_int4_v1_2_m_axis 1 4 3 N 710 N 710 3010
preplace netloc axis_sg_int4_v1_3_m_axis 1 4 3 N 1050 2320 1380 2970
preplace netloc axis_signal_gen_v6_4_m_axis 1 4 1 1850 1370n
preplace netloc axis_signal_gen_v6_5_m_axis 1 4 1 1850 1670n
preplace netloc axis_switch_0_M00_AXIS 1 3 1 1160J -350n
preplace netloc axis_switch_0_M01_AXIS 1 3 1 1140J -330n
preplace netloc axis_switch_0_M02_AXIS 1 3 1 1130 -310n
preplace netloc axis_switch_0_M03_AXIS 1 3 1 1120 -290n
preplace netloc axis_switch_avg_M00_AXIS 1 9 1 4570 910n
preplace netloc axis_switch_buf_M00_AXIS 1 9 1 4580 1170n
preplace netloc axis_switch_gen_M04_AXIS 1 3 1 1050 -270n
preplace netloc axis_switch_gen_M05_AXIS 1 3 1 1030 -250n
preplace netloc axis_tproc64x32_x8_0_m0_axis 1 1 2 270 0 630
preplace netloc axis_tproc64x32_x8_0_m1_axis 1 2 1 N 480
preplace netloc axis_tproc64x32_x8_0_m2_axis 1 2 1 690 500n
preplace netloc axis_tproc64x32_x8_0_m3_axis 1 2 1 680J 520n
preplace netloc axis_tproc64x32_x8_0_m4_axis 1 2 1 670J 540n
preplace netloc axis_tproc64x32_x8_0_m5_axis 1 2 1 660J 560n
preplace netloc axis_tproc64x32_x8_0_m6_axis 1 2 1 650J 580n
preplace netloc axis_tproc64x32_x8_0_m7_axis 1 2 1 640J 600n
preplace netloc axis_tproc64x32_x8_0_m8_axis 1 2 2 NJ 620 1010J
preplace netloc dac2_clk_1 1 6 5 3090 2050 N 2050 N 2050 N 2050 N
preplace netloc ps8_0_axi_periph_M00_AXI 1 3 3 1230 30 NJ 30 2290
preplace netloc ps8_0_axi_periph_M01_AXI 1 3 3 1230 910 NJ 910 2320
preplace netloc ps8_0_axi_periph_M02_AXI 1 3 3 1220 1200 NJ 1200 2310
preplace netloc ps8_0_axi_periph_M03_AXI 1 3 3 1230 1230 NJ 1230 2300
preplace netloc ps8_0_axi_periph_M05_AXI 1 5 4 NJ -3380 NJ -3380 NJ -3380 4250
preplace netloc ps8_0_axi_periph_M06_AXI 1 5 4 NJ -3360 NJ -3360 NJ -3360 4180
preplace netloc ps8_0_axi_periph_M07_AXI 1 2 4 730 -3010 NJ -3010 1920J -2970 2260
preplace netloc ps8_0_axi_periph_M08_AXI 1 5 2 NJ -3320 3090
preplace netloc ps8_0_axi_periph_M12_AXI 1 1 5 240 -20 NJ -20 NJ -20 NJ -20 2280
preplace netloc ps8_0_axi_periph_M13_AXI 1 5 2 NJ -3220 3060
preplace netloc sysref_in_1 1 6 5 3080 2030 N 2030 N 2030 N 2030 N
preplace netloc usp_rf_data_converter_0_m20_axis 1 6 2 3100 280 3440
preplace netloc usp_rf_data_converter_0_vout00 1 7 4 N 2260 NJ 2260 NJ 2260 NJ
preplace netloc usp_rf_data_converter_0_vout10 1 7 4 N 2280 NJ 2280 NJ 2280 NJ
preplace netloc usp_rf_data_converter_0_vout11 1 7 4 N 2300 NJ 2300 NJ 2300 NJ
preplace netloc usp_rf_data_converter_0_vout12 1 7 4 N 2320 NJ 2320 NJ 2320 NJ
preplace netloc usp_rf_data_converter_0_vout13 1 7 4 N 2340 NJ 2340 NJ 2340 NJ
preplace netloc usp_rf_data_converter_0_vout20 1 7 4 N 2360 N 2360 N 2360 N
preplace netloc usp_rf_data_converter_0_vout21 1 7 4 N 2380 N 2380 N 2380 N
preplace netloc usp_rf_data_converter_0_vout22 1 7 4 N 2400 N 2400 N 2400 N
preplace netloc usp_rf_data_converter_0_vout23 1 7 4 N 2420 N 2420 N 2420 N
preplace netloc usp_rf_data_converter_0_vout30 1 7 4 N 2440 N 2440 N 2440 N
preplace netloc usp_rf_data_converter_0_vout31 1 7 4 N 2460 N 2460 N 2460 N
preplace netloc vin20_1 1 6 5 3070J 2020 N 2020 N 2020 N 2020 4980
preplace netloc zynq_ultra_ps_e_0_M_AXI_HPM0_FPD 1 4 1 1860 -2920n
preplace netloc zynq_ultra_ps_e_0_M_AXI_HPM1_FPD 1 4 1 1850 -3670n
preplace netloc axis_sg_mux4_v2_0_m_axis 1 4 3 1850J 2020 NJ 2020 2960
preplace netloc axis_cc_sg_6_M_AXIS 1 3 1 N 1930
preplace netloc axi_smc_M13_AXI 1 3 3 1210 900 NJ 900 2270
levelinfo -pg 1 -140 40 450 870 1540 2080 2670 3280 3980 4410 4790 5000
pagesize -pg 1 -db -bbox -sgen -290 -3820 5150 3620
"
}

  # Restore current instance
  current_bd_instance $oldCurInst

  validate_bd_design
  save_bd_design
}
# End of create_root_design()


##################################################################
# MAIN FLOW
##################################################################

create_root_design ""


