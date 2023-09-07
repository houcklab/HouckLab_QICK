module axis_pfb_readout_v1
	( 
		// AXI Slave I/F for configuration.
		s_axi_aclk		,
		s_axi_aresetn	,

		s_axi_awaddr	,
		s_axi_awprot	,
		s_axi_awvalid	,
		s_axi_awready	,

		s_axi_wdata		,
		s_axi_wstrb		,
		s_axi_wvalid	,
		s_axi_wready	,

		s_axi_bresp		,
		s_axi_bvalid	,
		s_axi_bready	,

		s_axi_araddr	,
		s_axi_arprot	,
		s_axi_arvalid	,
		s_axi_arready	,

		s_axi_rdata		,
		s_axi_rresp		,
		s_axi_rvalid	,
		s_axi_rready	,

		// s_* and m_* reset/clock.
		aclk			,
		aresetn			,

    	// S_AXIS for input samples
		s_axis_tvalid	,
		s_axis_tready	,
		s_axis_tdata	,

		// M_AXIS for CH0 output.
		m0_axis_tvalid	,
		m0_axis_tdata	,

		// M_AXIS for CH1 output.
		m1_axis_tvalid	,
		m1_axis_tdata	,

		// M_AXIS for CH2 output.
		m2_axis_tvalid	,
		m2_axis_tdata	,

		// M_AXIS for CH3 output.
		m3_axis_tvalid	,
		m3_axis_tdata	,

		// M_AXIS for CH4 output.
		m4_axis_tvalid	,
		m4_axis_tdata	,

		// M_AXIS for CH5 output.
		m5_axis_tvalid	,
		m5_axis_tdata	,

		// M_AXIS for CH6 output.
		m6_axis_tvalid	,
		m6_axis_tdata	,

		// M_AXIS for CH7 output.
		m7_axis_tvalid	,
		m7_axis_tdata
	);

/*********/
/* Ports */
/*********/
input				s_axi_aclk;
input				s_axi_aresetn;

input	[5:0]		s_axi_awaddr;
input	[2:0]		s_axi_awprot;
input				s_axi_awvalid;
output				s_axi_awready;

input	[31:0]		s_axi_wdata;
input	[3:0]		s_axi_wstrb;
input				s_axi_wvalid;
output				s_axi_wready;

output	[1:0]		s_axi_bresp;
output				s_axi_bvalid;
input				s_axi_bready;

input	[5:0]		s_axi_araddr;
input	[2:0]		s_axi_arprot;
input				s_axi_arvalid;
output				s_axi_arready;

output	[31:0]		s_axi_rdata;
output	[1:0]		s_axi_rresp;
output				s_axi_rvalid;
input				s_axi_rready;

input				aresetn;
input				aclk;

input				s_axis_tvalid;
output				s_axis_tready;
input 	[4*32-1:0]	s_axis_tdata;

output				m0_axis_tvalid;
output	[31:0]		m0_axis_tdata;

output				m1_axis_tvalid;
output	[31:0]		m1_axis_tdata;

output				m2_axis_tvalid;
output	[31:0]		m2_axis_tdata;

output				m3_axis_tvalid;
output	[31:0]		m3_axis_tdata;

output				m4_axis_tvalid;
output	[31:0]		m4_axis_tdata;

output				m5_axis_tvalid;
output	[31:0]		m5_axis_tdata;

output				m6_axis_tvalid;
output	[31:0]		m6_axis_tdata;

output				m7_axis_tvalid;
output	[31:0]		m7_axis_tdata;

/********************/
/* Internal signals */
/********************/
// Registers.
wire	[31:0]	FREQ0_REG;
wire	[31:0]	FREQ1_REG;
wire	[31:0]	FREQ2_REG;
wire	[31:0]	FREQ3_REG;
wire	[31:0]	FREQ4_REG;
wire	[31:0]	FREQ5_REG;
wire	[31:0]	FREQ6_REG;
wire	[31:0]	FREQ7_REG;
wire	[1:0]	OUTSEL_REG;

// Output data.
wire				tvalid_i;
wire	[8*32-1:0]	tdata_i;
wire	[31:0]		dout_v [0:7];

/**********************/
/* Begin Architecture */
/**********************/
// AXI Slave.
axi_slv axi_slv_i
	(
		.aclk			(s_axi_aclk	 	),
		.aresetn		(s_axi_aresetn	),

		// Write Address Channel.
		.awaddr			(s_axi_awaddr 	),
		.awprot			(s_axi_awprot 	),
		.awvalid		(s_axi_awvalid	),
		.awready		(s_axi_awready	),

		// Write Data Channel.
		.wdata			(s_axi_wdata	),
		.wstrb			(s_axi_wstrb	),
		.wvalid			(s_axi_wvalid   ),
		.wready			(s_axi_wready	),

		// Write Response Channel.
		.bresp			(s_axi_bresp	),
		.bvalid			(s_axi_bvalid	),
		.bready			(s_axi_bready	),

		// Read Address Channel.
		.araddr			(s_axi_araddr 	),
		.arprot			(s_axi_arprot 	),
		.arvalid		(s_axi_arvalid	),
		.arready		(s_axi_arready	),

		// Read Data Channel.
		.rdata			(s_axi_rdata	),
		.rresp			(s_axi_rresp	),
		.rvalid			(s_axi_rvalid	),
		.rready			(s_axi_rready	),

		// Registers.
		.FREQ0_REG		(FREQ0_REG		), 
		.FREQ1_REG		(FREQ1_REG		), 
		.FREQ2_REG		(FREQ2_REG		), 
		.FREQ3_REG		(FREQ3_REG		), 
		.FREQ4_REG		(FREQ4_REG		), 
		.FREQ5_REG		(FREQ5_REG		), 
		.FREQ6_REG		(FREQ6_REG		), 
		.FREQ7_REG		(FREQ7_REG		), 
		.OUTSEL_REG		(OUTSEL_REG		)
	);

// PFB with DDS product.
pfb_dds pfb_dds_i
	(
		// Reset and clock.
		.aresetn		(aresetn		),
		.aclk			(aclk			),

		// S_AXIS for input data.
		.s_axis_tready	(s_axis_tready	),
		.s_axis_tvalid	(s_axis_tvalid	),
		.s_axis_tdata	(s_axis_tdata	),

		// M_AXIS for output data.
		.m_axis_tvalid	(tvalid_i		),
		.m_axis_tdata	(tdata_i		),

		// Registers.
		.FREQ0_REG		(FREQ0_REG		), 
		.FREQ1_REG		(FREQ1_REG		), 
		.FREQ2_REG		(FREQ2_REG		), 
		.FREQ3_REG		(FREQ3_REG		), 
		.FREQ4_REG		(FREQ4_REG		), 
		.FREQ5_REG		(FREQ5_REG		), 
		.FREQ6_REG		(FREQ6_REG		), 
		.FREQ7_REG		(FREQ7_REG		), 
		.OUTSEL_REG		(OUTSEL_REG		)
	);

generate
genvar ii;
for (ii = 0; ii < 8; ii = ii + 1) begin
	assign dout_v[ii] 	= tdata_i[ii*32 +: 32];
end
endgenerate

// Assign outputs.
assign m0_axis_tvalid 	= tvalid_i;
assign m0_axis_tdata	= dout_v[0];

assign m1_axis_tvalid 	= tvalid_i;
assign m1_axis_tdata	= dout_v[1];

assign m2_axis_tvalid 	= tvalid_i;
assign m2_axis_tdata	= dout_v[2];

assign m3_axis_tvalid 	= tvalid_i;
assign m3_axis_tdata	= dout_v[3];

assign m4_axis_tvalid 	= tvalid_i;
assign m4_axis_tdata	= dout_v[4];

assign m5_axis_tvalid 	= tvalid_i;
assign m5_axis_tdata	= dout_v[5];

assign m6_axis_tvalid 	= tvalid_i;
assign m6_axis_tdata	= dout_v[6];

assign m7_axis_tvalid 	= tvalid_i;
assign m7_axis_tdata	= dout_v[7];

endmodule

