import Pyro4
from qick import QickConfig

def makeProxy(IP):
    Pyro4.config.SERIALIZER = "pickle"
    Pyro4.config.PICKLE_PROTOCOL_VERSION=4

    ns_host = IP
    ns_port = 8888
    server_name = "myqick"

    ns = Pyro4.locateNS(host=ns_host, port=ns_port)

    # print the nameserver entries: you should see the QickSoc proxy
    for k,v in ns.list().items():
        print(k,v)

    soc = Pyro4.Proxy(ns.lookup(server_name))
    soccfg = QickConfig(soc.get_cfg())
    return(soc, soccfg)