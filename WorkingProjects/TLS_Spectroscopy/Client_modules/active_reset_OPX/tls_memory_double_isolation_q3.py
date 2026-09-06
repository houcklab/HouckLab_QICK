import production_tls_memory_smoke_q3 as runner


runner.RUN_NAME = "TLS_memory_double_isolation"
runner.SEQUENCES = ("double",)


if __name__ == "__main__":
    runner.main()
