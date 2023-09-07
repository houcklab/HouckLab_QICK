import h5py
import numpy as np
import matplotlib.pyplot as plt

outerFolder = "Y:\Shashwat\Data\Protomon\FMV7_A2\\"
#Y:\Shashwat\Data\Protomon\FMV7_A2\dataTestSpecVsFlux\dataTestSpecVsFlux_2022_09_21
outerFolder = outerFolder + '\\dataTestSpecVsFlux\\dataTestSpecVsFlux_2022_09_21\\'
fileName = outerFolder + 'dataTestSpecVsFlux_2022_09_21_00_12_16_data.h5'
# Look at a data file
with h5py.File(fileName, "r") as f:
    # List all groups
    print("Keys: %s" % f.keys())
    a_group_key = list(f.keys())[1]
    print("Viewing data file")

    ### Make arrays according to what you want to plot, e.g. what's inside the data object
    ### This example is spec vs. flux 2D plot

    voltVec = np.array(f['voltVec'])
    transdata_I = np.array(f['trans_Imat'])
    transdata_Q = np.array(f['trans_Qmat'])
    trans_fpts = np.array(f['trans_fpts'])
    specdata_I = np.array(f['spec_Imat'])
    specdata_Q = np.array(f['spec_Qmat'])
    spec_fpts = np.array(f['spec_fpts'])

    X_trans = (trans_fpts / 1e6) / 1e3
    X_trans_step = X_trans[1] - X_trans[0]
    X_spec = spec_fpts / 1e3
    X_spec_step = X_spec[1] - X_spec[0]
    Y = voltVec
    Y_step = Y[1] - Y[0]
    Z_trans = np.full((len(voltVec), len(trans_fpts)), np.nan)
    Z_spec1 = np.full((len(voltVec), len(spec_fpts)), np.nan)
    Z_spec2 = np.full((len(voltVec), len(spec_fpts)), np.nan)

    ### create the figure and subplots that data will be plotted on
    fig, axs = plt.subplots(3, 1, figsize=(8, 12))
    #### plot out the transmission data

    for i in range(len(voltVec)):

        sig = transdata_I[i,:] + 1j * transdata_Q[i,:]
        avgamp0 = np.abs(sig)
        Z_trans[i, :] = avgamp0
        # axs[0].plot(x_pts, avgamp0, label="Amplitude; ADC 0")
        ax_plot_0 = axs[0].imshow(
            Z_trans,
            aspect='auto',
            extent=[np.min(X_trans) - X_trans_step / 2, np.max(X_trans) + X_trans_step / 2, np.min(Y) - Y_step / 2,
                    np.max(Y) + Y_step / 2],
            origin='lower',
            interpolation='none',
        )
        if i == 0:  #### if first sweep add a colorbar
            cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
            cbar0.set_label('a.u.', rotation=90)
        else:
            cbar0.remove()
            cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
            cbar0.set_label('a.u.', rotation=90)

        axs[0].set_ylabel("yoko voltage (V)")
        axs[0].set_xlabel("Cavity Frequency (GHz)")
        axs[0].set_title("Cavity Transmission")


        #### plot out the spec data in phase quadrature
        sig = specdata_I[i,:] + 1j * specdata_Q[i,:]
        #avgphase = np.angle(sig) - np.mean(np.angle(sig))
        avgphase = np.arctan2(specdata_Q[i,:],specdata_I[i,:]) - np.mean(np.arctan2(specdata_Q[i,:],specdata_I[i,:]))
        Z_spec1[i, :] = avgphase
        ax_plot_1 = axs[1].imshow(
            Z_spec1,
            aspect='auto',
            extent=[np.min(X_spec) - X_spec_step / 2, np.max(X_spec) + X_spec_step / 2, np.min(Y) - Y_step / 2,
                    np.max(Y) + Y_step / 2],
            origin='lower',
            interpolation='none',
        )

        #### plot out the spec data background subtracted
        sig = specdata_I[i,:] + 1j * specdata_Q[i,:]
        avgamp0 = np.abs(sig) - np.mean(np.abs(sig))
        Z_spec2[i, :] = avgamp0
        ax_plot_2 = axs[2].imshow(
            Z_spec2,
            aspect='auto',
            extent=[np.min(X_spec) - X_spec_step / 2, np.max(X_spec) + X_spec_step / 2, np.min(Y) - Y_step / 2,
                    np.max(Y) + Y_step / 2],
            origin='lower',
            interpolation='none',
        )
        if i == 0:  #### if first sweep add a colorbar
            cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
            cbar1.set_label('a.u.', rotation=90)
            cbar2 = fig.colorbar(ax_plot_2, ax=axs[2], extend='both')
            cbar2.set_label('a.u.', rotation=90)
        else:
            cbar1.remove()
            cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
            cbar1.set_label('a.u.', rotation=90)
            cbar2.remove()
            cbar2 = fig.colorbar(ax_plot_2, ax=axs[2], extend='both')
            cbar2.set_label('a.u.', rotation=90)

        axs[1].set_ylabel("yoko voltage (V)")
        axs[1].set_xlabel("Spec Frequency (GHz)")
        axs[1].set_title("Qubit Spec Phase Bkgnd Sub")
        axs[2].set_ylabel("yoko voltage (V)")
        axs[2].set_xlabel("Spec Frequency (GHz)")
        axs[2].set_title("Qubit Spec Mag Bkgnd Sub")

    plt.tight_layout()
    plt.savefig(outerFolder +"testfig.png")  #### save the figure
