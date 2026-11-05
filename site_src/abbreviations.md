*[RFSoC]: Radio-frequency system-on-chip: the Xilinx board that generates the microwave pulses and digitises the readout signal
*[QICK]: Quantum Instrumentation Control Kit: the open-source firmware and Python library that run on the RFSoC
*[tProc]: QICK's timed processor, which runs the compiled pulse program (v1 on the lab board; one clock cycle is 2.32515 ns)
*[TWPA]: Travelling-wave parametric amplifier on the readout line, biased by a current yoko and pumped by the Windfreak SynthHD
*[DAC]: Digital-to-analogue converter: an RFSoC output channel. Gains are in DAC units, 0 to 32767 (full scale)
*[ADC]: Analogue-to-digital converter: the RFSoC input that digitises the readout signal
*[IQ]: In-phase and quadrature: the two components of the demodulated readout signal
*[FF]: Fast flux. A historical suffix on class names: no current experiment plays a fast-flux pulse
*[MUX]: Multiplexed readout. A historical suffix on class names: these classes read one resonator
*[SS]: Single shot: one IQ point per shot instead of an average
*[HMM]: Hidden Markov model: a two-state model fitted to a parity record to estimate the switching rate
*[ACF]: Autocorrelation function: its decay gives the parity switching rate
*[PSD]: Power spectral density: its Lorentzian corner gives the parity switching rate
*[SNR]: Signal-to-noise ratio
*[QND]: Quantum non-demolition: repeated readouts give the same answer
*[ZSP]: Zero-span parity: two-tone parity measurement with readout and drive at fixed frequencies
*[MR]: Modified Ramsey: a fixed-wait Ramsey sequence that maps charge parity onto the qubit state
*[MRC]: Modified Ramsey control: the sweet-spot null control for Modified Ramsey
*[CW]: Continuous wave: a tone that stays on instead of being pulsed
*[PMOD]: Expansion connector on the RFSoC board; pin 0 is a trigger output of the tProc
*[yoko]: Yokogawa GS200 source: GPIB1::9 sets the charge bias (voltage), GPIB1::12 the TWPA bias (current)
