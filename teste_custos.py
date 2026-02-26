# -*- coding: utf-8 -*-

import subprocess
import time
import requests
import json

def ler_tabela(porta: int):
    """Puxa /routes do roteador e retorna o routing_table"""
    try:
        r = requests.get(f"http://localhost:{porta}/routes", timeout=3)
        if r.status_code != 200:
            return None
        data = r.json()
        return data.get("routing_table", None)
    except Exception:
        return None


def filtrar_rotas(tabela: dict, prefixos_interesse):
    """Filtra e ordena só as rotas de interesse"""
    if not tabela:
        return {}

    out = {}
    for dest in prefixos_interesse:
        if dest in tabela:
            info = tabela[dest]
            out[dest] = {
                "cost": info.get("cost"),
                "next_hop": info.get("next_hop"),
            }
        else:
            out[dest] = None
    return out


def print_snapshot(rotas_por_router):
    print("\n>>>>>>>>> SNAPSHOT <<<<<<<<<")
    for nome, rotas in rotas_por_router.items():
        print(f"\n--- {nome} ---")
        print(json.dumps(rotas, indent=2, ensure_ascii=False))


def teste_custos_sem_falha():
    print(">>>>>>>>> TESTE DE CUSTOS <<<<<<<<<")

    cfg_r1 = "exemplo/config_A.csv"  # R1 (5000) vizinhos: 5001 (1), 5002 (10)
    cfg_r2 = "exemplo/config_B.csv"  # R2 (5001) vizinhos: 5000 (1), 5002 (2)
    cfg_r3 = "exemplo/config_C.csv"  # R3 (5002) vizinhos: 5000 (10), 5001 (2)

    processos = []
    try:
        print("[*] Subindo R1 (5000)...")
        processos.append(subprocess.Popen([
            "python3", "roteador.py",
            "-p", "5000",
            "-f", cfg_r1,
            "--network", "10.0.0.0/24",
            "--interval", "3"
        ]))

        print("[*] Subindo R2 (5001)...")
        processos.append(subprocess.Popen([
            "python3", "roteador.py",
            "-p", "5001",
            "-f", cfg_r2,
            "--network", "10.0.1.0/24",
            "--interval", "3"
        ]))

        print("[*] Subindo R3 (5002)...")
        processos.append(subprocess.Popen([
            "python3", "roteador.py",
            "-p", "5002",
            "-f", cfg_r3,
            "--network", "10.0.2.0/24",
            "--interval", "3"
        ]))

        # espera subirem
        time.sleep(3)

        # rotas que queremos observar
        interesse = [
            "10.0.0.0/24",
            "10.0.1.0/24",
            "10.0.2.0/24",
        ]

        print("\n[*] Observando evolução dos custos por alguns ciclos...")
        # pega snapshots a cada 3s
        for t in range(1, 7):
            tab_r1 = ler_tabela(5000)
            tab_r2 = ler_tabela(5001)
            tab_r3 = ler_tabela(5002)

            snap = {
                "R1 (5000)": filtrar_rotas(tab_r1, interesse),
                "R2 (5001)": filtrar_rotas(tab_r2, interesse),
                "R3 (5002)": filtrar_rotas(tab_r3, interesse),
            }

            print(f"\n⏱️  Snapshot {t}/6")
            print_snapshot(snap)

            time.sleep(3)

        # injeta uma rota nova falsa anunciada por R2,
        # pra ver R1 e R3 aprendendo via Bellman-Ford (custo acumulado).
        print("\n[*] (Opcional) Injetando uma rota nova via atualização do R2...")
        update_data = {
            "sender_address": "127.0.0.1:5001",
            "routing_table": {
                "172.16.0.0/24": {"cost": 4, "next_hop": "127.0.0.1:5001"}
            }
        }
        r = requests.post("http://localhost:5000/receive_update", json=update_data, timeout=5)
        print(f"[*] POST injeção em R1 via 'sender=R2': status {r.status_code}")

        interesse2 = interesse + ["172.16.0.0/24"]
        for t in range(1, 5):
            tab_r1 = ler_tabela(5000)
            tab_r2 = ler_tabela(5001)
            tab_r3 = ler_tabela(5002)

            snap = {
                "R1 (5000)": filtrar_rotas(tab_r1, interesse2),
                "R2 (5001)": filtrar_rotas(tab_r2, interesse2),
                "R3 (5002)": filtrar_rotas(tab_r3, interesse2),
            }

            print(f"\n⏱️  Pós-injeção {t}/4")
            print_snapshot(snap)

            time.sleep(3)

        print("\n✅ Teste concluído.")

    except KeyboardInterrupt:
        print("\n[!] Interrompido pelo usuário.")

    finally:
        print("\n[*] Encerrando roteadores...")
        for p in processos:
            try:
                p.terminate()
            except Exception:
                pass
        for p in processos:
            try:
                p.wait(timeout=3)
            except Exception:
                pass
        print("[*] Finalizado.")


if __name__ == "__main__":
    teste_custos_sem_falha()