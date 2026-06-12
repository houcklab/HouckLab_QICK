from qick.pyro import make_proxy


def makeProxy():
    return make_proxy(
        ns_host="192.168.1.146",
        ns_port=8888,
        proxy_name="myqick",
        remote_traceback=True,
    )


if __name__ == "__main__":
    soc, soccfg = makeProxy()
    print(soccfg)
