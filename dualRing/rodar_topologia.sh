#!/bin/bash

echo "Testando Topologia Dual Ring"
echo ""

cd ..

start_router() {
    local num=$1
    local net=$2
    local port=$3

    echo "Iniciando R$num na porta $port..."
    python3 roteador.py -p $port -f dualRing/R$num.csv --network $net --interval 5 &
    sleep 1
}

echo "Iniciando roteadores..."

start_router 1 "10.0.0.0/24" 5001
start_router 2 "10.0.1.0/24" 5002
start_router 3 "10.0.2.0/24" 5003
start_router 4 "10.0.3.0/24" 5004
start_router 5 "10.0.4.0/24" 5005
start_router 6 "10.0.5.0/24" 5006
start_router 7 "10.0.6.0/24" 5007
start_router 8 "10.0.7.0/24" 5008
start_router 9 "10.0.8.0/24" 5009
start_router 10 "10.0.9.0/24" 5010
start_router 11 "10.0.10.0/24" 5011
start_router 12 "10.0.11.0/24" 5012

echo ""
echo "Todos os roteadores iniciados!"
echo ""
echo "Para verificar:"
echo "curl http://localhost:5001/routes"
echo ""
echo "Para parar:"
echo "pkill -f roteador.py"

wait
