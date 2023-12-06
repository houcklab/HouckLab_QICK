# Source: https://gitlab.com/LBL-QubiC/QubicCali2021a/-/blob/master/chip57/wiremap.py
# Source of qchip: https://gitlab.com/LBL-QubiC/QubicCali2021a/-/blob/master/chip57/qubitcfg.json

chanmapqubit={'Q0.rdrv':0
		,'Q0.qdrv':2
		,'Q0.read':4
		}
ttydev={"qdrvlo":{"deviceid":"a4spi_02","hostname":"192.168.1.24","default":{"chan":3,"freq":5.4e9}}
        ,"readlo":{"deviceid":"a4spi_02","hostname":"192.168.1.24","default":{"chan":1,"freq":6.52e9}}
		,"readvat":{"deviceid":"attn3","hostname":"192.168.1.24","default":0}
        #,"readlo":{"deviceid":"multifreqlo_v1","hostname":"192.168.1.24","default":{"chan":2,"freq":6.52e9}}
		}
lor=6.52e9
#lor=6.52e9
loq=5.4e9
lofreq={'Q0.rdrv':lor
		,'Q0.qdrv':loq
		,'Q0.read':lor
		,'alignment.read':lor
		,'alignment.rdrv':lor
		,'vna.read':lor
		,'vna.rdrv':lor
		}
dacelementsdest=['Q0.rdrv','Q0.qdrv']
lo0elementsdest=['Q0.read','Q3.read','Q6.read']
lo1elementsdest=['Q1.read','Q4.read','Q7.read']
lo2elementsdest=['Q2.read','Q5.read']
gatesall=['Q0X90','Q0read']
elementlistall={'Q0.qdrv':0,'Q0.read':8,'Q0.rdrv':0}
destlistall={'Q0.qdrv':1,'Q0.read':4,'Q0.rdrv':0}
patchlistall={'Q0.rdrv':8e-9,'Q0.read':8e-9,'Q0.qdrv':8e-9}
patchmaxlistall={'Q0.rdrv':100,'Q0.read':100,'Q0.qdrv':100}
patchdict=patchmaxlistall
elemdict=elementlistall
destdict=destlistall

gates=[
'Q0read'
'Q0X90']
