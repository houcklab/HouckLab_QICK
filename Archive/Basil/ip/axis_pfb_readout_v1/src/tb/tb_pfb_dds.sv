module tb();

// Number of Lanes (Input).
parameter L = 4;

reg					aresetn;
reg					aclk;

wire				s_axis_tready;
reg					s_axis_tvalid;
reg	[L*32-1:0]		s_axis_tdata;

wire				m_axis_tvalid;
wire[2*L*32-1:0]	m_axis_tdata;

reg	[31:0]			FREQ0_REG;
reg	[31:0]			FREQ1_REG;
reg	[31:0]			FREQ2_REG;
reg	[31:0]			FREQ3_REG;
reg	[31:0]			FREQ4_REG;
reg	[31:0]			FREQ5_REG;
reg	[31:0]			FREQ6_REG;
reg	[31:0]			FREQ7_REG;
reg	[1:0]			OUTSEL_REG;

// TB Control
reg tb_data 		= 0;
reg tb_data_done 	= 0;
reg tb_write_out 	= 0;

// Input data.
reg	[31:0]	din_ii [0:L-1];

// Output data.
wire[31:0]	dout_ii [0:2*L-1];

generate
genvar ii;
for (ii = 0; ii < L; ii = ii + 1) begin
    assign s_axis_tdata[32*ii +: 32] = din_ii[ii];
	// Real.
	assign dout_ii[ii] 	= m_axis_tdata[ii*32 +: 32];
	assign dout_ii[L+ii]= m_axis_tdata[(L+ii)*32 +: 32];
end
endgenerate

// DUT.
pfb_dds DUT
	(
		// Reset and clock.
		.aresetn		(aresetn		),
		.aclk			(aclk			),

		// S_AXIS for input data.
		.s_axis_tready	(s_axis_tready	),
		.s_axis_tvalid	(s_axis_tvalid	),
		.s_axis_tdata	(s_axis_tdata	),

		// M_AXIS for output data.
		.m_axis_tvalid	(m_axis_tvalid	),
		.m_axis_tdata	(m_axis_tdata	),

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

initial begin
	// Reset sequence.
	aresetn		<= 0;
	FREQ0_REG	<= 0;
	FREQ1_REG	<= 0;
	FREQ2_REG	<= 0;
	FREQ3_REG	<= 0;
	FREQ4_REG	<= 0;
	FREQ5_REG	<= 0;
	FREQ6_REG	<= 0;
	FREQ7_REG	<= 0;
	OUTSEL_REG	<= 0;
	#500;
	aresetn	<= 1;

	// Set frequency to be 10 MHz for Channel 1.
	FREQ1_REG	= freq_calc(100, 10);

	#100;

	tb_data 		<= 1;
	tb_write_out 	<= 1;
	wait (tb_data_done);
	tb_write_out 	<= 0;

	#1000;
end

// Load coefficients.
initial begin
	int fd, i;
	bit signed [15:0] vali, valq;
	s_axis_tvalid 	<= 0;
	s_axis_tdata	<= 0;

	// Open file with Coefficients.
	fd = $fopen("../../../../../tb/data_iq.txt","r");

	wait(tb_data);
	@(posedge aclk);
	
	i = 0;
	while ($fscanf(fd,"%d,%d", vali, valq) == 2) begin
		//$display("T = %d, i = %d, I = %d, Q = %d", $time, i, vali, valq);		
		din_ii[i] <= {valq,vali};
		i = i + 1;
		if (i == 4) begin
		    i = 0;
			@(posedge aclk);
			s_axis_tvalid <= 1;
		end
	end

	@(posedge aclk);
	s_axis_tvalid <= 0;
	tb_data_done <= 1;

end

// Write output into file.
initial begin
	int fd;
	int i;
	shortint real_d, imag_d;

	// Output file.
	fd = $fopen("../../../../../tb/dout.csv","w");

	// Data format.
	$fdisplay(fd, "valid, real, imag");

	wait (tb_write_out);

	while (tb_write_out) begin
		@(posedge aclk);
		for (i=0; i<2*L; i = i+1) begin
			real_d = dout_ii[i][15:0];
			imag_d = dout_ii[i][31:16];
			$fdisplay(fd, "%d, %d, %d", m_axis_tvalid, real_d, imag_d);
		end
	end

	$display("Closing file, t = %0t", $time);
	$fclose(fd);
end

always begin
	aclk <= 0;
	#5;
	aclk <= 1;
	#5;
end  

// Function to compute frequency register.
function [31:0] freq_calc;
    input int fclk;
    input int f;
    
	// All input frequencies are in MHz.
	real fs,temp;
	fs = fclk;
	temp = f/fs*2**30;
	freq_calc = {int'(temp),2'b00};
endfunction
endmodule

