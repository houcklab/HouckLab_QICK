module pfb_dds
	(
		// Reset and clock.
		aresetn			,
		aclk			,

		// S_AXIS for input data.
		s_axis_tready	,
		s_axis_tvalid	,
		s_axis_tdata	,

		// M_AXIS for output data.
		m_axis_tvalid	,
		m_axis_tdata	,

		// Registers.
		FREQ0_REG		,
		FREQ1_REG		,
		FREQ2_REG		,
		FREQ3_REG		,
		FREQ4_REG		,
		FREQ5_REG		,
		FREQ6_REG		,
		FREQ7_REG		,
		OUTSEL_REG
	);

/*********/
/* Ports */
/*********/
input				aresetn;
input				aclk;

output				s_axis_tready;
input				s_axis_tvalid;
input	[4*32-1:0]	s_axis_tdata;

output				m_axis_tvalid;
output	[8*32-1:0]	m_axis_tdata;

input	[31:0]		FREQ0_REG;
input	[31:0]		FREQ1_REG;
input	[31:0]		FREQ2_REG;
input	[31:0]		FREQ3_REG;
input	[31:0]		FREQ4_REG;
input	[31:0]		FREQ5_REG;
input	[31:0]		FREQ6_REG;
input	[31:0]		FREQ7_REG;
input	[1:0]		OUTSEL_REG;

/********************/
/* Internal signals */
/********************/

wire				tvalid_i;
wire	[8*32-1:0]	tdata_i;

/**********************/
/* Begin Architecture */
/**********************/
pfb
	#(
		.L(4)
	)
	pfb_i
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
		.m_axis_tdata	(tdata_i		)
	);

ddsprod_v ddsprod_v_i
	(
		// Reset and clock.
		.aresetn		(aresetn		),
		.aclk			(aclk			),

		// S_AXIS for input data.
		.s_axis_tvalid	(tvalid_i		),
		.s_axis_tdata	(tdata_i		),

		// M_AXIS for output data.
		.m_axis_tvalid	(m_axis_tvalid	),
		.m_axis_tdata	(m_axis_tdata	),

		// Registers.
		.FREQ0_REG		(FREQ0_REG 		),
		.FREQ1_REG		(FREQ1_REG		), 
		.FREQ2_REG		(FREQ2_REG		), 
		.FREQ3_REG		(FREQ3_REG		), 
		.FREQ4_REG		(FREQ4_REG		), 
		.FREQ5_REG		(FREQ5_REG		), 
		.FREQ6_REG		(FREQ6_REG		), 
		.FREQ7_REG		(FREQ7_REG		), 
		.OUTSEL_REG		(OUTSEL_REG		)
	);

endmodule

