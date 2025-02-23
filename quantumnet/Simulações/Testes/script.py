from quantumnet.components import Network, Host
from quantumnet.objects import Qubit, Logger
import json
import sys
import random

# Captura o número de rounds a partir dos argumentos (opcional)
rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 1

# Ativa o Logger
Logger.activate(Logger)

# Inicializa uma nova rede
Logger.get_instance().log(f"Simulação inicializando...")
rede = Network()
rede.set_ready_topology("Grade", 3, 4)
rede.draw()

# Define os hosts
alice = rede.get_host(1)
bob = rede.get_host(2)

# Obtém a fidelidade inicial dos pares EPR entre Alice e Bob
initial_epr_pairs = rede.get_eprs_from_edge(alice.host_id, bob.host_id)
initial_fidelity = None
if initial_epr_pairs:
    initial_fidelity = initial_epr_pairs[-1].get_current_fidelity()

# Informações do canal
channel_info = rede.get_channel_info(alice.host_id, bob.host_id)
canal_tipo = channel_info.get('type', 'desconhecido')


# if canal_tipo not in ['X', 'Z', 'Y']:
#     Logger.get_instance().log(f"Canal do tipo '{canal_tipo}' ignorado. Simulação não será executada para este canal.")
#     result = {
#         "simulation": rounds,
#         "status": "ignored",
#         "reason": f"Canal do tipo '{canal_tipo}' não avaliado."
#     }
#     print(json.dumps(result, indent=4))
#     sys.exit(1)  # Continua a execução das próximas simulações sem interrupção

# Gera uma request de fidelidade alvo aleatória
request = 0.95 #random.uniform(0.75, 0.96)

# Estima o número de rounds necessários para atingir a fidelidade alvo
rounds_estimation = rede.linklayer.round_estimates(alice.host_id, bob.host_id, request, "symmetric")
required_rounds = rounds_estimation.get("symmetric", {}).get("rounds", rounds)

Logger.get_instance().log(f"Fidelidade inicial: {initial_fidelity}")
Logger.get_instance().log(f"Request de fidelidade alvo: {request}")
Logger.get_instance().log(f"Tipo de canal: {canal_tipo}")
Logger.get_instance().log(f"Estimativa de rounds necessários: {required_rounds}")

# Executa o agendamento de purificação com os rounds estimados
success = rede.linklayer.purification_scheduling(alice.host_id, bob.host_id, 'symmetric', required_rounds)

# Obtém a fidelidade final após o agendamento
final_epr_pairs = rede.get_eprs_from_edge(alice.host_id, bob.host_id)
final_fidelity = None
if final_epr_pairs:
    final_fidelity = final_epr_pairs[-1].get_current_fidelity()



if final_fidelity is not None and final_fidelity >= request:
    success = True
    Logger.get_instance().log(f"Purificação bem-sucedida: Fidelidade final ({final_fidelity}) >= Request ({request}).")
else:
    success = False
    Logger.get_instance().log(f"Purificação falhou: Fidelidade final ({final_fidelity}) < Request ({request}).")

# Loga o sucesso ou falha da purificação e fidelidade final
Logger.get_instance().log(f"Sucesso da purificação: {success}")
Logger.get_instance().log(f"Fidelidade final: {final_fidelity}")

# Armazena o resultado da simulação em JSON
result = {
    "simulation": rounds,
    "success": success,
    "estimated_rounds": required_rounds,
    "request": request,
    "channel_info": canal_tipo,
    "initial_fidelity": initial_fidelity,
    "final_fidelity": final_fidelity
}

rede.linklayermetrics(
    simulation_number=rounds,
    success=success,
    metrics_requested=["Timeslot Total", "EPRs Criados", "Pares Eprs Consumidos", "Fidelidade Média dos Eprs"],
    output_type="csv"  # Retorna as métricas como um dicionário
)

# Apenas imprime o JSON do resultado, sem outras saídas
print(json.dumps(result, indent=4))
