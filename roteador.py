# -*- coding: utf-8 -*-

import copy
import csv
import json
import threading
import time
from argparse import ArgumentParser

import requests
from flask import Flask, jsonify, request

INFINITY = 16

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
        if '/' not in str(net):
            continue

        hop = info.get('next_hop')
        cost = info.get('cost', INFINITY)
        if hop is None or cost >= INFINITY:
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
        self.route_timeout = 90

        self.routing_table = {
            self.my_network: {'cost': 0,
                              'next_hop': self.my_address, 
                              'last_update': time.time()}
        }

        # Adiciona vizinhos diretos conhecidos pelo arquivo CSV
        for neighbor, cost in self.neighbors.items():
            if neighbor not in self.routing_table:
                self.routing_table[neighbor] = {'cost': cost,
                                                'next_hop': neighbor, 
                                                'last_update': time.time()}

        print("Tabela de roteamento inicial:")
        print(json.dumps(self.routing_table, indent=4))

        # Inicia o processo de atualização periódica em uma thread separada
        self._start_periodic_updates()
        self._start_timeout_checker()

    def _start_timeout_checker(self):
        t = threading.Thread(target=self._timeout_loop)
        t.daemon = True
        t.start()

    def _timeout_loop(self):
        while True:
            time.sleep(5)
            now = time.time()
            to_delete = []
            for net, route in self.routing_table.items():
                if net == self.my_network:
                    continue

                if now - route["last_update"] > self.route_timeout:
                    route["cost"] = INFINITY
                    route["last_update"] = now # Reseta o timer para a deleção
                    print(f"--- Rota {net} expirou e foi marcada como INFINITY ---")
                if route["cost"] >= INFINITY and (now - route["last_update"] > 30):
                    to_delete.append(net)

            for net in to_delete:
                del self.routing_table[net]
                print(f"--- Rota {net} removida da tabela (Garbage Collection) ---")

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
                self.send_updates_to_neighbors()
            except Exception as e:
                print(f"Erro durante a atualização periódida: {e}")   
    
    def send_updates_to_neighbors(self):
        """
        Envia a tabela de roteamento (potencialmente sumarizada) para todos os vizinhos.
        """    
        # cria cópia
        summarized = summarize_routing_table(copy.deepcopy(self.routing_table))

        for neighbor in self.neighbors:

            table_to_send = {}

            for net, info in summarized.items():

                # SPLIT HORIZON
                #if info["next_hop"] == neighbor:
                 #   continue
                #Poison Reverse
                if info["next_hop"] == neighbor:
        
                    poisoned_info = info.copy()
                    poisoned_info["cost"] = INFINITY
                    table_to_send[net] = poisoned_info

                else:
                    table_to_send[net] = info

            payload = {
                "sender_address": self.my_address,
                "routing_table": table_to_send
            }

            try:
                requests.post(
                    f"http://{neighbor}/receive_update",
                    json=payload,
                    timeout=3
                )
            except:
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
   
        try:
            if '/' in network and '/' in router_instance.my_network:
                my_net_ip, my_net_pref = parse_network(router_instance.my_network)
                rx_net_ip, rx_net_pref = parse_network(network)
                
                # Se a rede recebida (rx) tem máscara menor (é mais genérica)
                if rx_net_pref < my_net_pref:
                    mask = ((1 << 32) - 1) << (32 - rx_net_pref) & 0xFFFFFFFF
                    # Se a minha rede está contida na rede recebida, eu ignoro para evitar loop
                    if (my_net_ip & mask) == (rx_net_ip & mask):
                        print(f"--- [AVISO] Ignorando sumarização {network} que engloba minha rede local ---")
                        continue
        except Exception as e:
            print(f"Erro ao validar prefixo: {e}")

        neighbor_cost = info["cost"]
        new_cost = link_cost + neighbor_cost

        if neighbor_cost >= INFINITY:
            new_cost = INFINITY

        current_route = router_instance.routing_table.get(network)

        if current_route is None:
            if new_cost < INFINITY:
                router_instance.routing_table[network] = {
                    "cost": new_cost,
                    "next_hop": sender_address,
                    "last_update": time.time()
                }
                updated = True

        elif new_cost < current_route['cost']:
            router_instance.routing_table[network] = {
                'cost': new_cost,
                'next_hop': sender_address,
                'last_update': time.time()  
            }
            updated = True

        elif current_route['next_hop'] == sender_address:
            if current_route['cost'] != new_cost:
                router_instance.routing_table[network]['cost'] = new_cost
                router_instance.routing_table[network]['last_update'] = time.time()  
                updated = True

    if updated:
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
