import subprocess
import time
import requests
import json

ROUTER_URL = "http://localhost:5000"


def enviar_rotas(rotas, descricao):
    print(f"\n=== {descricao} ===")
    requests.post(
        f"{ROUTER_URL}/receive_update",
        json={
            "sender_address": "127.0.0.1:5001",
            "routing_table": rotas
        },
        timeout=5
    )

    time.sleep(6)

    tabela = requests.get(f"{ROUTER_URL}/routes").json()["routing_table"]
    print(json.dumps(tabela, indent=2))


def teste_sumarizacao():
    print("=== TESTE COMPLETO DE SUMARIZAÇÃO ===")

    process = subprocess.Popen([
        'python3', 'roteador.py',
        '-p', '5000',
        '-f', 'exemplo/config_A.csv',
        '--network', '10.0.0.0/24',
        '--interval', '5'
    ])

    time.sleep(3)

    try:

        # ================================
        # TESTE 1 — SUMARIZAÇÃO BÁSICA
        # ================================
        enviar_rotas(
            {
                "10.0.4.0/24": {"cost": 1, "next_hop": "127.0.0.1:5000"},
                "10.0.5.0/24": {"cost": 1, "next_hop": "127.0.0.1:5000"}
            },
            "Teste 1 — /24 → /23"
        )

        # ================================
        # TESTE 2 — MULTI-LEVEL SUMMARIZATION
        # ================================
        enviar_rotas(
            {
                "10.0.6.0/24": {"cost": 1, "next_hop": "127.0.0.1:5000"},
                "10.0.7.0/24": {"cost": 1, "next_hop": "127.0.0.1:5000"}
            },
            "Teste 2 — Criando /22"
        )

        # ================================
        # TESTE 3 — REDES NÃO ADJACENTES
        # NÃO deve resumir
        # ================================
        enviar_rotas(
            {
                "172.16.1.0/24": {"cost": 2, "next_hop": "127.0.0.1:5000"},
                "172.16.3.0/24": {"cost": 2, "next_hop": "127.0.0.1:5000"}
            },
            "Teste 3 — Não adjacentes (não sumariza)"
        )

        # ================================
        # TESTE 4 — ALINHAMENTO CIDR
        # Caso clássico de bug
        # ================================
        enviar_rotas(
            {
                "192.168.1.0/24": {"cost": 2, "next_hop": "127.0.0.1:5000"},
                "192.168.2.0/24": {"cost": 2, "next_hop": "127.0.0.1:5000"}
            },
            "Teste 4 — Falha de alinhamento (não deve resumir)"
        )

        # ================================
        # TESTE 5 — VIZINHOS DIFERENTES
        # NÃO deve resumir
        # ================================
        print("\n=== Teste 5 — Vizinhos diferentes ===")

        requests.post(
            f"{ROUTER_URL}/receive_update",
            json={
                "sender_address": "127.0.0.1:5001",
                "routing_table": {
                    "200.0.0.0/24": {"cost": 1, "next_hop": "127.0.0.1:5000"}
                }
            }
        )

        requests.post(
            f"{ROUTER_URL}/receive_update",
            json={
                "sender_address": "127.0.0.1:5002",
                "routing_table": {
                    "200.0.1.0/24": {"cost": 1, "next_hop": "127.0.0.1:5000"}
                }
            }
        )

        time.sleep(6)

        tabela = requests.get(f"{ROUTER_URL}/routes").json()["routing_table"]
        print(json.dumps(tabela, indent=2))

        print("\n✅ TODOS OS TESTES FINALIZADOS")

    finally:
        process.terminate()
        process.wait()


if __name__ == '__main__':
    teste_sumarizacao()