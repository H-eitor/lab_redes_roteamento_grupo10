import subprocess
import time
import requests
import json

def teste_count_to_infinity():
    print(">>>>>>>>> TESTE COUNT-TO-INFINITY <<<<<<<<<")

    r1 = subprocess.Popen([
        'python3', 'roteador.py',
        '-p', '5000',
        '-f', 'exemplo/config_A.csv',
        '--network', '10.0.0.0/24',
        '--interval', '5'
    ])

    r2 = subprocess.Popen([
        'python3', 'roteador.py',
        '-p', '5001',
        '-f', 'exemplo/config_B.csv',
        '--network', '10.0.1.0/24',
        '--interval', '5'
    ])

    r3 = subprocess.Popen([
        'python3', 'roteador.py',
        '-p', '5002',
        '-f', 'exemplo/config_C.csv',
        '--network', '10.0.2.0/24',
        '--interval', '5'
    ])

    time.sleep(8)

    print("\n>>>>>>>>> Simulando queda do R3...")
    r3.terminate()
    r3.wait()

    print("⏳ Aguardando propagação da falha...")
    time.sleep(25)

    try:
        r1_table = requests.get("http://localhost:5000/routes").json()["routing_table"]
        r2_table = requests.get("http://localhost:5001/routes").json()["routing_table"]

        print("\n=== TABELA R1 ===")
        print(json.dumps(r1_table, indent=2))

        print("\n=== TABELA R2 ===")
        print(json.dumps(r2_table, indent=2))

        print("\n🔎 Verificando se NÃO houve count-to-infinity...")

        ok = True
        for table in [r1_table, r2_table]:
            for route, info in table.items():
                if "10.0.2.0" in route and info["cost"] < 16:
                    ok = False

        if ok:
            print("\n✅ PASSOU — rota ficou INFINITY corretamente")
        else:
            print("\n❌ FALHOU — ainda existe loop")

    finally:
        r1.terminate()
        r2.terminate()
        r1.wait()
        r2.wait()

        print("\n>>>>>>>>> TESTE FINALIZADO <<<<<<<<<")


if __name__ == "__main__":
    teste_count_to_infinity()