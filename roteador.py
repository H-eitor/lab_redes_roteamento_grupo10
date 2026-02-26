# -*- coding: utf-8 -*-

import csv
import json
import threading
import time
from argparse import ArgumentParser

import requests
from flask import Flask, jsonify, request

INFINITY = 16
ROUTE_TIMEOUT = 15

def ip_to_int(ip_str):
    """Converte o ip em um inteiro de 32 bits"""
    parts = list(map(int, ip_str.split('.')))
    return (parts[0] << 24) + (parts[1] << 16) + (parts[2] << 8) + parts[3]
    
def int_to_ip(ip_int):
    """Faz o caminho inverso, converte de inteiro para ip"""
    ip_int &= 0xFFFFFFFF
    return f"{(ip_int >> 24) & 255}.{(ip_int >> 16) & 255}.{(ip_int >> 8) & 255}.{ip_int & 255}"

def parse_network(network_str):
    """Separa o ip em endereço e máscara"""
    ip_part, prefix = network_str.split('/')
    return ip_to_int(ip_part), int(prefix)

def can_summarize(net1_str, net2_str):
    ip1, pref1 = parse_network(net1_str)
    ip2, pref2 = parse_network(net2_str)

    if pref1 != pref2 or pref1 <= 0:
        return False, None

    mask = ((1 << 32) - 1) << (32 - pref1) & 0xFFFFFFFF
    base1 = ip1 & mask
    base2 = ip2 & mask

    block = 1 << (32 - pref1)

    # precisam ser adjacentes
    if abs(base1 - base2) != block:
        return False, None

    new_prefix = pref1 - 1
    super_block = 1 << (32 - new_prefix)

    new_base = min(base1, base2)

    # garante alinhamento da super-rede
    if new_base % super_block != 0:
        return False, None

    return True, f"{int_to_ip(new_base)}/{new_prefix}"

def summarize_routing_table(table):
    """Sumariza as rotas da tabela"""

    # Nada pra sumarizar
    if len(table) < 2:
        return {k: dict(v) for k, v in table.items()}
    
    summary = {k: dict(v) for k, v in table.items()}

    """Só sumariza rotas que vão para o mesmo vizinho"""
    by_neighbor = {}
    for net, info in summary.items():
        if '/' not in net:
            continue

        hop = info['next_hop']
        if hop is None:
            continue

        if '/' in str(hop):
            continue

        cost = info.get('cost', 0)
        if isinstance(cost, (int, float)) and cost >= 16:
            continue

        by_neighbor.setdefault(hop, []).append(net)

    for hop, nets in by_neighbor.items():
        nets.sort(key=lambda x: parse_network(x)[0])

        i = 0
        while i < len(nets) - 1:
            net1, net2 = nets[i], nets[i+1]
            # Verifica se é possível sumarizar
            can_merge, new_net = can_summarize(net1, net2)

            if not can_merge:
                i += 1
                continue

            new_cost = max(summary[net1]['cost'], summary[net2]['cost'])

            del summary[net1]
            del summary[net2]
            summary[new_net] = {'cost': new_cost, 'next_hop': hop, "last_update": time.time()}

            print(f"--- Sucesso: {net1} + {net2} viraram {new_net} ---")

            nets.pop(i)
            nets.pop(i)
            nets.insert(i, new_net)

    return summary

class Router:
    """
    Representa um roteador que executa o algoritmo de Vetor de Distância.
    """

    def __init__(self, my_address, neighbors, my_network, update_interval=1):
        """
        Inicializa o roteador.

        :param my_address: O endereço (ip:porta) deste roteador.
        :param neighbors: Um dicionário contendo os vizinhos diretos e o custo do link.
                          Ex: {'127.0.0.1:5001': 5, '127.0.0.1:5002': 10}
        :param my_network: A rede que este roteador administra diretamente.
                           Ex: '10.0.1.0/24'
        :param update_interval: O intervalo em segundos para enviar atualizações, o tempo que o roteador espera 
                                antes de enviar atualizações para os vizinhos.        """
        self.my_address = my_address
        self.neighbors = neighbors
        self.my_network = my_network
        self.update_interval = update_interval

        self.routing_table = {
            self.my_network: {'cost': 0, 'next_hop': self.my_address, "last_update": time.time()}
        }

        # Adiciona vizinhos diretos conhecidos pelo arquivo CSV
        for neighbor, cost in self.neighbors.items():
            if neighbor not in self.routing_table:
                self.routing_table[neighbor] = {'cost': cost, 'next_hop': neighbor, "last_update": time.time()}

        print("Tabela de roteamento inicial:")
        print(json.dumps(self.routing_table, indent=4))

        # Inicia o processo de atualização periódica em uma thread separada
        self._start_periodic_updates()

    def expire_routes(self):
        now = time.time()

        for dest, info in self.routing_table.items():

            if dest == self.my_network:
                continue

            last = info.get("last_update")
            if last is None:
                continue

            if now - last > ROUTE_TIMEOUT and info["cost"] < INFINITY:
                print(f"ROTA EXPIRADA: {dest}")
                info["cost"] = INFINITY 

    def _start_periodic_updates(self):
        """Inicia uma thread para enviar atualizações periodicamente."""
        thread = threading.Thread(target=self._periodic_update_loop)
        thread.daemon = True
        thread.start()

    def _periodic_update_loop(self):
        """Loop que envia atualizações de roteamento em intervalos regulares."""
        while True:
            time.sleep(self.update_interval)
            print(f"[{time.ctime()}] Enviando atualizações periódicas para os vizinhos...")
            try:
                self.expire_routes()
                self.send_updates_to_neighbors()
            except Exception as e:
                print(f"Erro durante a atualização periódida: {e}")   
    
    def send_updates_to_neighbors(self):
        """
        Envia a tabela de roteamento (potencialmente sumarizada) para todos os vizinhos.
        """      
        for neighbor_address in self.neighbors:

            tabela_para_enviar = summarize_routing_table(
                self.routing_table.copy()
            )

            tabela_filtrada = {}

            for dest, info in tabela_para_enviar.items():
                if info["next_hop"] == neighbor_address:
                    tabela_filtrada[dest] = {
                        "cost": INFINITY,
                        "next_hop": info["next_hop"]
                    }
                else:
                    tabela_filtrada[dest] = info

            payload = {
                "sender_address": self.my_address,
                "routing_table": tabela_filtrada
            }

            url = f'http://{neighbor_address}/receive_update'

            try:
                print(f"Enviando tabela para {neighbor_address}")
                requests.post(url, json=payload, timeout=5)
            except requests.exceptions.RequestException:
                pass

# --- API Endpoints ---
# Instância do Flask e do Roteador (serão inicializadas no main)
app = Flask(__name__)
router_instance = None

@app.route('/routes', methods=['GET'])
def get_routes():
    """Endpoint para visualizar a tabela de roteamento atual."""
    if router_instance:
        return jsonify({
            "message": "Não implementado!.",
            "vizinhos" : router_instance.neighbors,
            "my_network": router_instance.my_network,
            "my_address": router_instance.my_address,
            "update_interval": router_instance.update_interval,
            "routing_table": router_instance.routing_table
        })
    return jsonify({"error": "Roteador não inicializado"}), 500

@app.route('/receive_update', methods=['POST'])
def receive_update():
    """Endpoint que recebe atualizações de roteamento de um vizinho."""
    if not request.json:
        return jsonify({"error": "Invalid request"}), 400

    update_data = request.json
    sender_address = update_data.get("sender_address")
    sender_table = update_data.get("routing_table")

    if not sender_address or not isinstance(sender_table, dict):
        return jsonify({"error": "Missing sender_address or routing_table"}), 400

    print(f"Recebida atualização de {sender_address}:")
    print(json.dumps(sender_table, indent=4))

    if sender_address not in router_instance.neighbors:
        return jsonify({"status": "ignored"}), 200

    link_cost = router_instance.neighbors[sender_address]
    updated = False

    for network, info in sender_table.items():

        if network == router_instance.my_network:
            continue

        neighbor_cost = info["cost"]
        new_cost = min(link_cost + neighbor_cost, INFINITY)

        if network not in router_instance.routing_table:
            router_instance.routing_table[network] = {
                "cost": new_cost,
                "next_hop": sender_address,
                "last_update": time.time()
            }
            updated = True

        else:
            current_cost = router_instance.routing_table[network]["cost"]
            current_next_hop = router_instance.routing_table[network]["next_hop"]

            if new_cost < current_cost:
                router_instance.routing_table[network] = {
                    "cost": new_cost,
                    "next_hop": sender_address,
                    "last_update": time.time()
                }
                updated = True

            elif current_next_hop == sender_address and new_cost != current_cost:
                router_instance.routing_table[network]["cost"] = new_cost
                updated = True

    if updated:
        router_instance.routing_table = summarize_routing_table(
        router_instance.routing_table
        )
        print("Tabela de roteamento ATUALIZADA:")
        print(json.dumps(router_instance.routing_table, indent=4))

    return jsonify({"status": "success", "message": "Update received"}), 200

if __name__ == '__main__':
    parser = ArgumentParser(description="Simulador de Roteador com Vetor de Distância")
    parser.add_argument('-p', '--port', type=int, default=5000, help="Porta para executar o roteador.")
    parser.add_argument('-f', '--file', type=str, required=True, help="Arquivo CSV de configuração de vizinhos.")
    parser.add_argument('--network', type=str, required=True, help="Rede administrada por este roteador (ex: 10.0.1.0/24).")
    parser.add_argument('--interval', type=int, default=10, help="Intervalo de atualização periódica em segundos.")
    args = parser.parse_args()

    # Leitura do arquivo de configuração de vizinhos
    neighbors_config = {}
    try:
        with open(args.file, mode='r') as infile:
            reader = csv.DictReader(infile)
            for row in reader:
                neighbors_config[row['vizinho']] = int(row['custo'])
    except FileNotFoundError:
        print(f"Erro: Arquivo de configuração '{args.file}' não encontrado.")
        exit(1)
    except (KeyError, ValueError) as e:
        print(f"Erro no formato do arquivo CSV: {e}. Verifique as colunas 'vizinho' e 'custo'.")
        exit(1)

    my_full_address = f"127.0.0.1:{args.port}"
    print("--- Iniciando Roteador ---")
    print(f"Endereço: {my_full_address}")
    print(f"Rede Local: {args.network}")
    print(f"Vizinhos Diretos: {neighbors_config}")
    print(f"Intervalo de Atualização: {args.interval}s")
    print("--------------------------")

    router_instance = Router(
        my_address=my_full_address,
        neighbors=neighbors_config,
        my_network=args.network,
        update_interval=args.interval
    )

    # Inicia o servidor Flask
    app.run(host='0.0.0.0', port=args.port, debug=False)