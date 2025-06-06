import Pyro4
from qick import QickConfig

def makeProxy():
    Pyro4.config.SERIALIZER = "pickle"
    Pyro4.config.PICKLE_PROTOCOL_VERSION=4

    ns_host = "192.168.1.11"
    ns_port = 8888
    server_name = "myqick"

    ns = Pyro4.locateNS(host=ns_host, port=ns_port)

    # print the nameserver entries: you should see the QickSoc proxy
    for k,v in ns.list().items():
        print(k,v)

    soc = Pyro4.Proxy(ns.lookup(server_name))
    soccfg = QickConfig(soc.get_cfg())
    return(soc, soccfg)

def makeProxy_RFSOC_10():
    Pyro4.config.SERIALIZER = "pickle"
    Pyro4.config.PICKLE_PROTOCOL_VERSION=4

    ns_host = "192.168.1.10"
    ns_port = 8888
    server_name = "myqick"

    ns = Pyro4.locateNS(host=ns_host, port=ns_port)

    # print the nameserver entries: you should see the QickSoc proxy
    for k,v in ns.list().items():
        print(k,v)

    soc = Pyro4.Proxy(ns.lookup(server_name))
    soccfg = QickConfig(soc.get_cfg())
    print(soccfg)
    return(soc, soccfg)

def makeProxy_RFSOC_11():
    Pyro4.config.SERIALIZER = "pickle"
    Pyro4.config.PICKLE_PROTOCOL_VERSION=4

    ns_host = "192.168.1.11"
    ns_port = 8888
    server_name = "myqick"

    ns = Pyro4.locateNS(host=ns_host, port=ns_port)

    # print the nameserver entries: you should see the QickSoc proxy
    for k,v in ns.list().items():
        print(k,v)

    soc = Pyro4.Proxy(ns.lookup(server_name))
    soccfg = QickConfig(soc.get_cfg())
    return(soc, soccfg)

def makeProxy_RFSOC_12():
    Pyro4.config.SERIALIZER = "pickle"
    Pyro4.config.PICKLE_PROTOCOL_VERSION=4

    ns_host = "192.168.1.12"
    ns_port = 8888
    server_name = "myqick"

    ns = Pyro4.locateNS(host=ns_host, port=ns_port)

    # print the nameserver entries: you should see the QickSoc proxy
    for k,v in ns.list().items():
        print(k,v)

    soc = Pyro4.Proxy(ns.lookup(server_name))
    soccfg = QickConfig(soc.get_cfg())
    return(soc, soccfg)

def makeProxy_RFSOC_119():
    Pyro4.config.SERIALIZER = "pickle"
    Pyro4.config.PICKLE_PROTOCOL_VERSION=4

    ns_host = "192.168.1.119"
    ns_port = 8888
    server_name = "myqick"

    ns = Pyro4.locateNS(host=ns_host, port=ns_port)

    # print the nameserver entries: you should see the QickSoc proxy
    for k,v in ns.list().items():
        print(k,v)

    soc = Pyro4.Proxy(ns.lookup(server_name))
    soccfg = QickConfig(soc.get_cfg())
    return(soc, soccfg)

# soc, soccfg = makeProxy()
# print("debug")