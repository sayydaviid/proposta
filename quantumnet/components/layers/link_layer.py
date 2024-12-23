import networkx as nx
from quantumnet.components import Host
from quantumnet.objects import Logger, Epr
from random import uniform
import random
import difflib


class LinkLayer:
    def __init__(self, network, physical_layer):
        """
        Inicializa a camada de enlace.
        
        Args:
            network : Network : Rede.
            physical_layer : PhysicalLayer : Camada física.
        """
        self._network = network
        self._physical_layer = physical_layer
        self._requests = []
        self._failed_requests = []
        self.logger = Logger.get_instance()
        self.used_eprs = 0  # Inicializa o contador de EPRs utilizados
        self.used_qubits = 0  # Inicializa o contador de Qubits utilizados
        self.created_eprs = []  # Armazenar os EPRs criados pela camada física
        self.eprs_pairs_consumed = 0  # Contador de pares de EPRs consumidos
        self.eprs_pairs_created = 0  # Contador de pares de EPRs criados

    @property
    def requests(self):
        return self._requests

    @property
    def failed_requests(self):
        return self._failed_requests

    def __str__(self):
        """ Retorna a representação em string da camada de enlace. 
        
        Returns:
            str : Representação em string da camada de enlace.
        """
        return 'Link Layer'
    
    def get_used_eprs(self):
        self.logger.debug(f"Eprs usados na camada {self.__class__.__name__}: {self.used_eprs}")
        return self.used_eprs
    
    def get_used_qubits(self):
        self.logger.debug(f"Qubits usados na camada {self.__class__.__name__}: {self.used_qubits}")
        return self.used_qubits
    
    def request(self, alice_id: int, bob_id: int):
        """
        Solicitação de criação de emaranhamento entre Alice e Bob.
        
        Args:
            alice_id : int : Id do host Alice.
            bob_id : int : Id do host Bob.
        """
        try:
            alice = self._network.get_host(alice_id)
            bob = self._network.get_host(bob_id)
        except KeyError:
            self.logger.log(f'Host {alice_id} ou {bob_id} não encontrado na rede.')
            return False

        for attempt in range(1, 3):
            self._network.timeslot()
            self.logger.log(f'Timeslot {self._network.get_timeslot()}: Tentativa de emaranhamento entre {alice_id} e {bob_id}.')

            entangle = self._physical_layer.entanglement_creation_heralding_protocol(alice, bob)

            # Após cada tentativa de emaranhamento, transferimos os EPRs criados para a camada de enlace
            if entangle:
                self.used_eprs += 1
                self.used_qubits += 2
                self._requests.append((alice_id, bob_id))

                # Adiciona os EPRs criados pela camada física à lista de EPRs criados da camada de enlace
                if self._physical_layer.created_eprs:
                    self.created_eprs.extend(self._physical_layer.created_eprs)
                    self._physical_layer.created_eprs.clear()  # Limpa a lista da camada física
                
                self.logger.log(f'Timeslot {self._network.get_timeslot()}: Entrelaçamento criado entre {alice} e {bob} na tentativa {attempt}.')
                return True
            else:
                self.logger.log(f'Timeslot {self._network.get_timeslot()}: Entrelaçamento falhou entre {alice} e {bob} na tentativa {attempt}.')
                self._failed_requests.append((alice_id, bob_id))

        # Verifica se deve realizar a purificação após duas falhas
        if len(self._failed_requests) >= 2:
            purification_success = self.purification(alice_id, bob_id)
            
            # Independente de a purificação ser bem-sucedida ou não, sempre transferimos os EPRs criados
            if self._physical_layer.created_eprs:
                self.created_eprs.extend(self._physical_layer.created_eprs)
                self._physical_layer.created_eprs.clear()  # Limpa a lista da camada física
            
            return purification_success

        # Após a segunda tentativa, garante que todos os EPRs criados sejam transferidos
        if self._physical_layer.created_eprs:
            self.created_eprs.extend(self._physical_layer.created_eprs)
            self._physical_layer.created_eprs.clear()  # Limpa a lista da camada física
            
        return False

    def purification_calculator(self, f1: int, f2: int, purification_type: int) -> float:
        """
        Cálculo das fórmulas de purificação.
        
        Args:
            f1: int : Fidelidade do primeiro EPR.
            f2: int : Fidelidade do segundo EPR.
            purification_type: int : Fórmula escolhida (1 - Default, 2 - BBPSSW Protocol, 3 - DEJMPS Protocol).
        
        Returns:
            float : Fidelidade após purificação.
        """
        f1f2 = f1 * f2

        if purification_type == 1:
            self.logger.log('A purificação utilizada foi tipo 1.')
            return f1f2 / ((f1f2) + ((1 - f1) * (1 - f2)))

        elif purification_type == 2:
            result = (f1f2 + ((1 - f1) / 3) * ((1 - f2) / 3)) / (f1f2 + f1 * ((1 - f2) / 3) + f2 * ((1 - f1) / 3) + 5 * ((1 - f1) / 3) * ((1 - f2) / 3))
            self.logger.log('A purificação utilizada foi tipo 2.')
            return result

        elif purification_type == 3:
            result = (2 * f1f2 + 1 - f1 - f2) / ((1 / 4) * (f1 + f2 - f1f2) + 3 / 4)
            self.logger.log('A purificação utilizada foi tipo 3.')
            return result
        
        self.logger.log('Purificação só pode aceitar os valores (1, 2 ou 3), a fórmula 1 foi escolhida por padrão.')
        return f1f2 / ((f1f2) + ((1 - f1) * (1 - f2)))


    def purification(self, alice_id: int, bob_id: int, purification_type: int = 1):
        """
        Purificação de EPRs.

        Args:
            alice_id : int : Id do host Alice.
            bob_id : int : Id do host Bob.
            purification_type : int : Tipo de protocolo de purificação.
        """
        self._network.timeslot()  # Incrementa o timeslot para a tentativa de purificação

        eprs_fail = self._physical_layer.failed_eprs

        if len(eprs_fail) < 2:
            self.logger.log(f'Timeslot {self._network.get_timeslot()}: Não há EPRs suficientes para purificação no canal ({alice_id}, {bob_id}).')
            return False

        eprs_fail1 = eprs_fail[-1]
        eprs_fail2 = eprs_fail[-2]
        f1 = eprs_fail1.get_current_fidelity()
        f2 = eprs_fail2.get_current_fidelity()

        purification_prob = (f1 * f2) + ((1 - f1) * (1 - f2))

        # Incrementa a contagem de EPRs utilizados, pois ambos serão usados na tentativa de purificação
        self.used_eprs += 2
        self.used_qubits += 4

        if purification_prob > 0.5:
            new_fidelity = self.purification_calculator(f1, f2, purification_type)

            if new_fidelity > 0.8:  # Verifica se a nova fidelidade é maior que 0.8
                epr_purified = Epr((alice_id, bob_id), new_fidelity)
                self._physical_layer.add_epr_to_channel(epr_purified, (alice_id, bob_id))
                self._physical_layer.failed_eprs.remove(eprs_fail1)
                self._physical_layer.failed_eprs.remove(eprs_fail2)
                self.logger.log(f'EPRS Usados {self.used_eprs}')
                self.logger.log(f'Timeslot {self._network.get_timeslot()}: Purificação bem sucedida no canal ({alice_id}, {bob_id}) com nova fidelidade {new_fidelity}.')
                return True
            else:
                self._physical_layer.failed_eprs.remove(eprs_fail1)
                self._physical_layer.failed_eprs.remove(eprs_fail2)
                self.logger.log(f'Timeslot {self._network.get_timeslot()}: Purificação falhou no canal ({alice_id}, {bob_id}) devido a baixa fidelidade após purificação.')
                return False
        else:
            self._physical_layer.failed_eprs.remove(eprs_fail1)
            self._physical_layer.failed_eprs.remove(eprs_fail2)
            self.logger.log(f'Timeslot {self._network.get_timeslot()}: Purificação falhou no canal ({alice_id}, {bob_id}) devido a baixa probabilidade de sucesso da purificação.')
            return False

    # def avg_fidelity_on_linklayer(self):
    #     """
    #     Calcula a fidelidade média dos EPRs criados na camada de enlace.
        
    #     Returns:
    #         float : Fidelidade média dos EPRs da camada de enlace.
    #     """
    #     total_fidelity = 0
    #     total_eprs = len(self.created_eprs)

    #     for epr in self.created_eprs:   
    #         total_fidelity += epr.get_current_fidelity()

    #     if total_eprs == 0:
    #         self.logger.log('Não há EPRs criados na camada de enlace.')
    #         return 0


    #     avg_fidelity = total_fidelity / total_eprs
    #     self.logger.log(f'A fidelidade média dos EPRs criados na camada de enlace é {avg_fidelity}')
    #     return avg_fidelity
    
    def avg_fidelity_eprs(self):
        """
        Calcula a fidelidade média dos pares EPRs criados durante as purificações bem-sucedidas (pumping e symmetric).

        Returns:
            dict: Fidelidade média dos EPRs separados por tipo de purificação ("pumping" e "symmetric").
        """
        if not self.created_eprs:
            self.logger.log("Nenhum EPR criado para calcular a fidelidade média.")
            return {"symmetric": 0.0, "pumping": 0.0}

        fidelidades = [epr.get_current_fidelity() for epr in self.created_eprs]
        self.logger.log(f"Quantidade de eprs: {(len(fidelidades))}")
        fidelidade_media = sum(fidelidades) / len(fidelidades)
        
        self.logger.log(f"Fidelidade média dos EPRs criados: {fidelidade_media}")
        return {"media": fidelidade_media}
    
    
    def purification_scheduling(self, alice_id: int, bob_id: int, purification_type: str, rounds: int = 1, Policy: int = 1, Try: int = None):
        """
        Função de agendamento de purificação, que executa tanto a purificação simétrica quanto a pumping.

        Args:
            alice_id (int): ID do host Alice.
            bob_id (int): ID do host Bob.
            purification_type (str): Tipo de purificação a ser realizada ('symmetric' ou 'pumping').
            rounds (int): Número de rounds de purificação. Aplica-se apenas para purificação simétrica.
            Policy (int): Política de tentativas de purificação (1: uma tentativa; 2: múltiplas tentativas).
            Try (int): Número máximo de tentativas para a segunda política.

        Returns:
            bool: True se a purificação foi bem-sucedida, False caso contrário.
        """
        # Lógica de correção de erros de digitação e verificação de tipo
        valid_purification_types = ['symmetric', 'pumping']
        match = difflib.get_close_matches(purification_type.lower(), valid_purification_types, n=1, cutoff=0.6)
        if not match:
            self.logger.log("Tipo de purificação inválido. Escolha 'symmetric' ou 'pumping'.")
            return False
        purification_type_corrected = match[0]  

        # Lógica para cada tipo de purificação com as políticas
        if purification_type_corrected == 'symmetric':
            if Policy == 1:
                # Política padrão: tenta apenas uma vez
                return self.purification_symmetric(alice_id, bob_id, rounds)
            elif Policy == 2:
                # Política de múltiplas tentativas
                for attempt in range(Try):
                    if self.purification_symmetric(alice_id, bob_id, rounds):
                        return True
                    self.logger.log(f"Tentativa {attempt + 1}/{Try} falhou para purificação simétrica.")
                return False
        elif purification_type_corrected == 'pumping':
            if Policy == 1:
                # Política padrão: tenta apenas uma vez
                return self.purification_pumping(alice_id, bob_id, rounds)
            elif Policy == 2:
                # Política de múltiplas tentativas
                for attempt in range(Try):
                    if self.purification_pumping(alice_id, bob_id, rounds):
                        return True
                    self.logger.log(f"Tentativa {attempt + 1}/{Try} falhou para purificação por bombardeamento.")
                return False
        return False

    def scheduling_verify(self, alice_id: int, bob_id: int, rounds: int) -> bool:
        """
        Verifica se há a quantidade de EPRs necessários para a purificação e cria mais se necessário.

        Args:
            alice_id (int): ID do host Alice.
            bob_id (int): ID do host Bob.
            rounds (int): Número de rounds de purificação.

        Returns:
            bool: True se houver EPRs suficientes após a verificação, False caso contrário.
        """
        # Calcula o número necessário de EPRs baseado no número de rounds
        required_eprs = 2 ** rounds
        eprs = self._network.get_eprs_from_edge(alice_id, bob_id)
        available_eprs = len(eprs)
        
        # Verifica se a quantidade disponível é suficiente
        if available_eprs < required_eprs:
            missing_eprs = required_eprs - available_eprs
            self.logger.log(f"Não há EPRs suficientes para purificação. Necessário: {required_eprs}, Disponível: {available_eprs}. Criando {missing_eprs} EPRs adicionais.")
            
            # Cria os EPRs necessários e evita duplicação
            for _ in range(missing_eprs):
                new_epr = self._physical_layer.create_epr_pair(increment_timeslot=False)
                self.eprs_pairs_created += 1
                self._physical_layer.add_epr_to_channel(new_epr, (alice_id, bob_id))
                

            self.logger.log(f"Total de {missing_eprs} EPRs criados e adicionados ao canal entre {alice_id} e {bob_id}.")
            
            # Atualiza a lista de EPRs com os novos EPRs criados
            eprs = self._network.get_eprs_from_edge(alice_id, bob_id)
            self.used_eprs = len(eprs)  # Atualiza o contador de EPRs utilizados
            
        # Verificação final se os EPRs são suficientes
        if len(eprs) >= required_eprs:
            self.logger.log(f"Agora há EPRs suficientes para a purificação: {len(eprs)} disponíveis.")
            return True
        else:
            self.logger.log(f"Ainda não há EPRs suficientes após a criação. Disponíveis: {len(eprs)}, Necessários: {required_eprs}.")
            return False
        
        
    def purification_symmetric(self, alice_id: int, bob_id: int, rounds: int) -> bool:
        """
        Purificação Simétrica de EPRs.

        Args:
            alice_id (int): ID do host Alice.
            bob_id (int): ID do host Bob.
            rounds (int): Número de rounds de purificação.

        Returns:
            bool: True se a purificação foi bem-sucedida, False caso contrário.
        """
        # Verifica o nível de ruído do canal
        channel_info = self._network.get_channel_info(alice_id, bob_id)
        # if any(channel_info.get(f'prob_erro_{tipo}', 0.0) > 0.2 for tipo in ['X', 'Y', 'Z', 'XZ']):
        #     self.logger.log(f"Purificação abortada: Canal entre {alice_id} e {bob_id} é muito ruidoso.")
        #     return False

        self.logger.log(f"Iniciando purificação simétrica entre {alice_id} e {bob_id} para {rounds} rounds.")
        
        # Verifica e garante que há EPRs suficientes
        if not self.scheduling_verify(alice_id, bob_id, rounds):
            self.logger.log(f"Falha na verificação dos EPRs. Purificação abortada.")
            self.last_error = "EPRs insuficientes para purificação."
            return False


        # Pega os EPRs iniciais entre Alice e Bob
        eprs = self._network.get_eprs_from_edge(alice_id, bob_id)
        # Executa a purificação por rounds
        for round_num in range(rounds):
            self.logger.log(f"Timeslot {self._network.get_timeslot()} - Executando round {round_num + 1} de purificação simétrica.")
            
            # Determina o número necessário de EPRs para o round atual
            num_eprs_necessarios = 2 ** (rounds - round_num)

            if len(eprs) < num_eprs_necessarios:
                self.logger.log(f"Não há EPRs suficientes para purificação no round {round_num + 1}. Abortando.")
                self.last_error = "EPRs insuficientes para purificação."
                return False
            
            new_eprs = []  # Lista para armazenar os novos EPRs após purificação

            # Aplica purificação em pares de EPRs
            for i in range(0, num_eprs_necessarios, 2):
                epr1 = eprs[i]
                epr2 = eprs[i + 1]
                self.eprs_pairs_consumed += 2  # Incrementa os pares consumidos
                
                f1 = epr1.get_current_fidelity()
                f2 = epr2.get_current_fidelity()
                self.logger.log(f"Purificando par de EPRs: fidelidades {f1} e {f2}.")
                
                # Pega as informações do canal e tipo de erro
                canal_tipo = channel_info.get('type', 'desconhecido')

                # Determina a probabilidade de sucesso e a nova fidelidade com base no tipo de canal
                if canal_tipo in ['X', 'Z', 'Y']:
                    p_success = f1 * f2 + (1 - f1) * (1 - f2)
                    x = random.uniform(0, 1)
                    if p_success >= x:
                        new_fidelity = f1 * f2 / (f1 * f2 + (1 - f1) * (1 - f2))
                        self.logger.log(f"Round {round_num + 1} - Probabilidade de sucesso: {p_success} (Erro {canal_tipo}) - Fidelidade: {new_fidelity}")
                    else:
                        self.logger.log(f"Round {round_num + 1} - Purificação falhou devido à baixa probabilidade de sucesso: {p_success}.")
                        self.last_error = "Erro de probabilidade de sucesso."
                        return False
                elif canal_tipo == 'XZ':
                    # Estado de Werner
                    p_success = ((f1 + (1 - f1) / 3) * (f2 + (1 - f2) / 3) + (2 * (1 - f1) / 3) * (2 * (1 - f2) / 3))
                    x = random.uniform(0, 1)
                    if p_success >= x:
                        new_fidelity = (1 / p_success) * (f1 * f2 + ((1 - f1) / 3) * ((1 - f2) / 3))
                        self.logger.log(f"Round {round_num + 1} - Probabilidade de sucesso: {p_success} (Estado de Werner) - Fidelidade: {new_fidelity}")
                    else:
                        self.logger.log(f"Round {round_num + 1} - Purificação falhou devido à baixa probabilidade de sucesso: {p_success}.")
                        self.last_error = "Erro de probabilidade de sucesso."
                        return False
                else:
                    self.logger.log(f"Tipo de canal '{canal_tipo}' não identificado para a purificação.")
                    return False

                # Criação de um novo par EPR com fidelidade pós-purificação
                epr_purified = self._physical_layer.create_epr_pair(fidelity=new_fidelity, increment_timeslot=False)
                new_eprs.append(epr_purified)
                self.created_eprs.append(epr_purified)  # Adiciona o EPR purificado à lista de EPRs criados

            # Remove os EPRs antigos usados no round atual do canal
            try:
                self._physical_layer.remove_epr_from_channel(eprs[:num_eprs_necessarios], (alice_id, bob_id))
            except ValueError as e:
                self.logger.log(f"Erro ao remover EPRs do canal: {e}. Tentando continuar.")

            # Adiciona os novos EPRs purificados ao canal e substitui `eprs` para o próximo round
            for epr_purified in new_eprs:
                self._physical_layer.add_epr_to_channel(epr_purified, (alice_id, bob_id))
            
            # Atualizar a lista de EPRs para refletir os novos pares purificados
            eprs = new_eprs
            
            if round_num == 0:
                # Nunca aplica decoerência no primeiro round
                self.logger.log(f"Round {round_num + 1}: Decoerência não aplicada (primeiro round).")
                self._network.timeslot(Decoherence=False)
            elif round_num == rounds - 1:
                # Não aplica decoerência no último round
                self.logger.log(f"Round {round_num + 1}: Decoerência não aplicada (último round).")
                self._network.timeslot(Decoherence=False)
            else:
                # Aplica decoerência apenas nos rounds intermediários
                self.logger.log(f"Round {round_num + 1}: Decoerência aplicada (round intermediário).")
                self._network.timeslot(Decoherence=True)
                
            self.logger.log(f"Round {round_num + 1} de purificação concluído com sucesso.")

        # Certifica-se de que o número de EPRs após o último round é 1
        self.logger.log(f"Purificação simétrica entre {alice_id} e {bob_id} concluída com sucesso.")
        return True

    #TODO:Proposta
    
    # def purification_symmetric(self, alice_id: int, bob_id: int, rounds: int) -> bool:
    #     """
    #     Purificação Simétrica de EPRs com suporte à purificação auxiliar.

    #     Args:
    #         alice_id (int): ID do host Alice.
    #         bob_id (int): ID do host Bob.
    #         rounds (int): Número de rounds de purificação.

    #     Returns:
    #         bool: True se a purificação foi bem-sucedida, False caso contrário.
    #     """

    #     # Inicializa ou reseta o atributo de erro
    #     self.last_error = None
    #     aux_eprs = []  # Lista para armazenar EPRs criados pela função auxiliar
    #     aux_replaced = False  # Indica se a purificação auxiliar já foi usada como substituição

    #     # Verifica o nível de ruído do canal
    #     channel_info = self._network.get_channel_info(alice_id, bob_id)
    #     # if any(channel_info.get(f'prob_erro_{tipo}', 0.0) > 0.2 for tipo in ['X', 'Y', 'Z', 'XZ']):
    #     #     self.logger.log(f"Purificação abortada: Canal entre {alice_id} e {bob_id} é muito ruidoso.")
    #     #     return False

    #     self.logger.log(f"Iniciando purificação simétrica entre {alice_id} e {bob_id} para {rounds} rounds.")
        
    #     # Verifica e garante que há EPRs suficientes
    #     if not self.scheduling_verify(alice_id, bob_id, rounds):
    #         self.logger.log(f"Falha na verificação dos EPRs. Purificação abortada.")
    #         self.last_error = "Falha na verificação dos EPRs."
    #         return False

    #     # Função para simular a execução da purificação auxiliar
    #     def auxiliary_purification():
    #         aux_new_eprs = []
    #         self.logger.log(f"Iniciando purificação auxiliar para backup.")
    #         for _ in range(2 ** rounds):
    #             aux_epr1 = self._physical_layer.create_epr_pair(increment_timeslot=False)
    #             aux_epr2 = self._physical_layer.create_epr_pair(increment_timeslot=False)
    #             f1 = aux_epr1.get_current_fidelity()
    #             f2 = aux_epr2.get_current_fidelity()

    #             canal_tipo = channel_info.get('type', 'desconhecido')
    #             if canal_tipo in ['X', 'Z', 'Y']:
    #                 new_fidelity = f1 * f2 / (f1 * f2 + (1 - f1) * (1 - f2))
    #             elif canal_tipo == 'XZ':
    #                 p_success = ((f1 + (1 - f1) / 3) * (f2 + (1 - f2) / 3) + (2 * (1 - f1) / 3) * (2 * (1 - f2) / 3))
    #                 new_fidelity = (1 / p_success) * (f1 * f2 + ((1 - f1) / 3) * ((1 - f2) / 3))
    #             else:
    #                 continue

    #             aux_new_epr = self._physical_layer.create_epr_pair(fidelity=new_fidelity, increment_timeslot=False)
    #             aux_new_eprs.append(aux_new_epr)

    #         return aux_new_eprs

    #     aux_eprs = auxiliary_purification()
    #     eprs = self._network.get_eprs_from_edge(alice_id, bob_id)
        
    #     # Executa a purificação por rounds
    #     for round_num in range(rounds):
    #         self.logger.log(f"Timeslot {self._network.get_timeslot()} - Executando round {round_num + 1} de purificação simétrica.")
            
    #         # Determina o número necessário de EPRs para o round atual
    #         num_eprs_necessarios = 2 ** (rounds - round_num)

    #         if len(eprs) < num_eprs_necessarios:
    #             self.logger.log(f"Não há EPRs suficientes para purificação no round {round_num + 1}. Abortando.")
    #             self.last_error = "EPRs insuficientes para purificação."
    #             return False

    #         new_eprs = []
    #         i = 0

    #         while i < num_eprs_necessarios:
    #             epr1 = eprs[i]
    #             epr2 = eprs[i + 1]
    #             self.eprs_pairs_consumed += 2  # Incrementa os pares consumidos
                
    #             f1 = epr1.get_current_fidelity()
    #             f2 = epr2.get_current_fidelity()
    #             self.logger.log(f"Purificando par de EPRs: fidelidades {f1} e {f2}.")

    #             canal_tipo = channel_info.get('type', 'desconhecido')
    #             success = False

    #             if canal_tipo in ['X', 'Z', 'Y']:
    #                 p_success = f1 * f2 + (1 - f1) * (1 - f2)
    #                 if random.uniform(0, 1) <= p_success:
    #                     new_fidelity = f1 * f2 / (f1 * f2 + (1 - f1) * (1 - f2))
    #                     self.logger.log(f"Round {round_num + 1} - Probabilidade de sucesso: {p_success} (Erro {canal_tipo}) - Fidelidade: {new_fidelity}")
    #                     success = True
    #             elif canal_tipo == 'XZ':
    #                 p_success = ((f1 + (1 - f1) / 3) * (f2 + (1 - f2) / 3) + (2 * (1 - f1) / 3) * (2 * (1 - f2) / 3))
    #                 if random.uniform(0, 1) <= p_success:
    #                     new_fidelity = (1 / p_success) * (f1 * f2 + ((1 - f1) / 3) * ((1 - f2) / 3))
    #                     self.logger.log(f"Round {round_num + 1} - Probabilidade de sucesso: {p_success} (Erro {canal_tipo}) - Fidelidade: {new_fidelity}")
    #                     success = True
    #             else:
    #                 self.logger.log(f"Tipo de canal '{canal_tipo}' não identificado para purificação.")
    #                 self._physical_layer.remove_epr_from_channel(eprs, (alice_id, bob_id))
    #                 return False

    #             if not success:
    #                 self.logger.log(f"Round {round_num + 1} - Purificação falhou devido à baixa probabilidade de sucesso: {p_success}.")
    #                 self.last_error = "Erro de probabilidade de sucesso."
    #                 if len(aux_eprs) >= 2:

    #                     epr1_backup = aux_eprs.pop(0)
    #                     epr2_backup = aux_eprs.pop(0)
    #                     self._physical_layer.remove_epr_from_channel([epr1, epr2], (alice_id, bob_id))
    #                     self.logger.log(f"Substituição bem-sucedida. Tentando purificar novamente.")
    #                     self.logger.log(f"Purificando par de EPRs: fidelidades {epr1.get_current_fidelity()} e {epr2.get_current_fidelity()}")
    #                     epr1, epr2 = epr1_backup, epr2_backup

    #                     self.logger.log(f"Round {round_num + 1} - Probabilidade de sucesso: {p_success} (Erro {canal_tipo}) - Fidelidade: {epr1_backup.get_current_fidelity()}")
    #                 else:
    #                     self.logger.log(f"Erro: Não há backups suficientes para substituir os pares falhados.")
    #                     self.last_error = "Erro de probabilidade de sucesso."
    #                     return False

    #             # Após substituição, purificar o par com sucesso garantido
    #             if canal_tipo in ['X', 'Z', 'Y']:
    #                 new_fidelity = f1 * f2 / (f1 * f2 + (1 - f1) * (1 - f2))
                    
    #             elif canal_tipo == 'XZ':
    #                 new_fidelity = (1 / p_success) * (f1 * f2 + ((1 - f1) / 3) * ((1 - f2) / 3))
            
    #             epr_purified = self._physical_layer.create_epr_pair(fidelity=new_fidelity, increment_timeslot=False)
    #             new_eprs.append(epr_purified)
    #             i += 2

    #         self._physical_layer.remove_epr_from_channel(eprs[:num_eprs_necessarios], (alice_id, bob_id))
            
    #         # Atualizar a lista de EPRs para refletir os novos pares purificados
    #         eprs = new_eprs

    #         # Adiciona os novos EPRs purificados ao canal e substitui `eprs` para o próximo round
    #         for epr_purified in new_eprs:
    #             self._physical_layer.add_epr_to_channel(epr_purified, (alice_id, bob_id))
    #             self.created_eprs.append(epr_purified)  # Adiciona o EPR purificado à lista de EPRs criados        
            
    #         if round_num == 0:
    #             # Nunca aplica decoerência no primeiro round
    #             self.logger.log(f"Round {round_num + 1}: Decoerência não aplicada (primeiro round).")
    #             self._network.timeslot(Decoherence=False)
    #         elif round_num == rounds - 1:
    #             # Não aplica decoerência no último round
    #             self.logger.log(f"Round {round_num + 1}: Decoerência não aplicada (último round).")
    #             self._network.timeslot(Decoherence=False)
    #         else:
    #             # Aplica decoerência apenas nos rounds intermediários
    #             self.logger.log(f"Round {round_num + 1}: Decoerência aplicada (round intermediário).")
    #             self._network.timeslot(Decoherence=True)
                
    #         self.logger.log(f"Round {round_num + 1} de purificação concluído com sucesso.")
    #         self.last_error = None
            
    #     self.logger.log(f"Purificação simétrica entre {alice_id} e {bob_id} concluída com sucesso, a fidelidade final é {eprs[0].get_current_fidelity()}.")
    #     return True

    #TODO:Proposta
    
    def purification_pumping(self, alice_id: int, bob_id: int, rounds: int) -> bool:
        """
        Purificação por Bombardeamento (Pumping) de EPRs com suporte à purificação auxiliar.

        Args:
            alice_id (int): ID do host Alice.
            bob_id (int): ID do host Bob.
            rounds (int): Número de rounds de purificação.

        Returns:
            bool: True se a purificação foi bem-sucedida, False caso contrário.
        """

        # Inicializa ou reseta o atributo de erro
        self.last_error = None
        aux_eprs = []  # Lista para armazenar EPRs criados pela função auxiliar
        aux_replaced = False  # Indica se a purificação auxiliar já foi usada como substituição

        # Verifica o nível de ruído do canal
        channel_info = self._network.get_channel_info(alice_id, bob_id)
        # if any(channel_info.get(f'prob_erro_{tipo}', 0.0) > 0.2 for tipo in ['X', 'Y', 'Z', 'XZ']):
        #     self.logger.log(f"Purificação abortada: Canal entre {alice_id} e {bob_id} é muito ruidoso.")
        #     return False
        
        self.logger.log(f"Iniciando purificação por bombardeamento entre {alice_id} e {bob_id} para {rounds} rounds.")
        
        eprs = self._network.get_eprs_from_edge(alice_id, bob_id)
        new_epr = None

        self.logger.log(f"Iniciando purificação por bombardeamento entre {alice_id} e {bob_id} para {rounds} rounds.")

        for round_num in range(rounds):
            self.logger.log(f"Timeslot {self._network.get_timeslot()}: Executando round {round_num + 1} de purificação por bombardeamento.")

            if len(eprs) < 2:
                # Se não houver EPRs suficientes, cria novos
                missing_eprs = 2 - len(eprs)
                self.logger.log(f"Timeslot {self._network.get_timeslot()}: Faltam {missing_eprs} EPRs para o round {round_num + 1}. Criando mais EPRs...")
                for _ in range(missing_eprs):
                    new_base_epr = self._physical_layer.create_epr_pair(increment_timeslot=False)
                    self._physical_layer.add_epr_to_channel(new_base_epr, (alice_id, bob_id))
                    self.eprs_pairs_created += 1
                eprs = self._network.get_eprs_from_edge(alice_id, bob_id)
            
            # Seleção dos EPRs baseados no round atual
            if round_num == 0:
                epr1 = eprs[-2] if len(eprs) > 1 else self._physical_layer.create_epr_pair(increment_timeslot=False)
                epr2 = eprs[-1] if len(eprs) > 0 else self._physical_layer.create_epr_pair(increment_timeslot=False)
                self.logger.log(f"Round {round_num + 1}: Pegando dois EPRs base para purificação: f_base1 (fidelidade {epr1.get_current_fidelity()}) e f_base2 (fidelidade {epr2.get_current_fidelity()}).")
            else:
                epr1 = new_epr  # Usa o último EPR purificado
                epr2 = self._physical_layer.create_epr_pair(increment_timeslot=False)  # Cria um novo EPR base
                self.logger.log(f"Round {round_num + 1}: Pegando EPR purificado (fidelidade {epr1.get_current_fidelity()}) e criando novo EPR base (fidelidade {epr2.get_current_fidelity()}).")

            # Fidelidades dos dois EPRs
            f1 = epr1.get_current_fidelity()
            f2 = epr2.get_current_fidelity()
            self.logger.log(f"Purificando par de EPRs: fidelidades {f1} e {f2}.")

            # Determina a probabilidade de sucesso
            canal_tipo = channel_info.get('type', 'desconhecido')
            success = False
            new_fidelity = None

            if canal_tipo in ['X', 'Z', 'Y']:
                p_success = f1 * f2 + (1 - f1) * (1 - f2)
                if random.uniform(0, 1) <= p_success:
                    new_fidelity = f1 * f2 / (f1 * f2 + (1 - f1) * (1 - f2))
                    success = True
                    self.logger.log(f"Round {round_num + 1} - Sucesso: Probabilidade {p_success}, Nova Fidelidade: {new_fidelity}")
                else:
                    self.logger.log(f"Round {round_num + 1} - Falha: Probabilidade {p_success}.")
                    self.last_error = "Erro de probabilidade de sucesso."

            elif canal_tipo == 'XZ':
                p_success = ((f1 + (1 - f1) / 3) * (f2 + (1 - f2) / 3) + (2 * (1 - f1) / 3) * (2 * (1 - f2) / 3))
                if random.uniform(0, 1) <= p_success:
                    new_fidelity = (1 / p_success) * (f1 * f2 + ((1 - f1) / 3) * ((1 - f2) / 3))
                    success = True
                    self.logger.log(f"Round {round_num + 1} - Sucesso: Probabilidade {p_success}, Nova Fidelidade: {new_fidelity}")
                else:
                    self.logger.log(f"Round {round_num + 1} - Falha: Probabilidade {p_success}.")
                    self.last_error = "Erro de probabilidade de sucesso."

            else:
                self.logger.log(f"Tipo de canal desconhecido '{canal_tipo}'. Purificação falhou.")
                self.last_error = "Tipo de canal desconhecido."
                success = False

            self.eprs_pairs_consumed += 2

            if not success:
                if len(aux_eprs) >= 2:
                    
                    self._physical_layer.remove_epr_from_channel([epr1, epr2], (alice_id, bob_id))
                    
                    if round_num == 0:
                        epr1_backup = self._physical_layer.create_epr_pair(increment_timeslot=False)  # Primeiro EPR do backup
                        epr2_backup = self._physical_layer.create_epr_pair(increment_timeslot=False)  # Novo EPR criado no timeslot atual
                        self.logger.log(f"Substituindo EPRs falhados por pares de backup.")
                    else:
                        epr1_backup = aux_eprs.pop(0)  # Primeiro EPR do backup
                        epr2_backup = self._physical_layer.create_epr_pair(increment_timeslot=False)  # Novo EPR criado no timeslot atual
                        self.logger.log(f"Substituindo EPRs falhados por pares de backup.")
                    
                    f1, f2 = epr1_backup.get_current_fidelity(), epr2_backup.get_current_fidelity()
                    self.logger.log(f"Purificando par de EPRs: fidelidades {f1} e {f2}")

                    canal_tipo = channel_info.get('type', 'desconhecido')
                    if canal_tipo in ['X', 'Z', 'Y']:
                        new_fidelity = f1 * f2 / (f1 * f2 + (1 - f1) * (1 - f2))
                    elif canal_tipo == 'XZ':
                        p_success = ((f1 + (1 - f1) / 3) * (f2 + (1 - f2) / 3) + (2 * (1 - f1) / 3) * (2 * (1 - f2) / 3))
                        new_fidelity = (1 / p_success) * (f1 * f2 + ((1 - f1) / 3) * ((1 - f2) / 3))
                    else:
                        self.logger.log(f"Tipo de canal desconhecido '{canal_tipo}' durante a substituição.")
                        return False

                    success = True
                    self.logger.log(f"Substituição bem-sucedida: Fidelidade resultante {new_fidelity}")
                    new_epr = self._physical_layer.create_epr_pair(fidelity=new_fidelity, increment_timeslot=False)
                    self._physical_layer.add_epr_to_channel(new_epr, (alice_id, bob_id))
                    eprs = self._network.get_eprs_from_edge(alice_id, bob_id)
                    self.created_eprs.append(new_epr)  # Adiciona o EPR purificado à lista de EPRs criados
                    self._physical_layer.remove_epr_from_channel([epr1_backup, epr2_backup], (alice_id, bob_id)) 
                    eprs = [new_epr]
                else:
                    self.logger.log(f"Erro: Não há backups suficientes para substituir os pares falhados.")
                    self.last_error = "Erro de probabilidade de sucesso."
                    return False
                
            else:
                # Cria o novo EPR purificado e atualiza o canal
                new_epr = self._physical_layer.create_epr_pair(fidelity=new_fidelity, increment_timeslot=False)
                self._physical_layer.add_epr_to_channel(new_epr, (alice_id, bob_id))
                self._physical_layer.remove_epr_from_channel([epr1, epr2], (alice_id, bob_id))
                self.created_eprs.append(new_epr)  # Adiciona o EPR purificado à lista de EPRs criados
                eprs = [new_epr]
            
            if round_num == 0:
                # Nunca aplica decoerência no primeiro round
                self.logger.log(f"Round {round_num + 1}: Decoerência não aplicada (primeiro round).")
                self._network.timeslot(Decoherence=False)
                # Não aplica decoerência no último round
            elif round_num == rounds - 1:
                self.logger.log(f"Round {round_num + 1}: Decoerência não aplicada (último round).")
                self._network.timeslot(Decoherence=False)
            else:
                # Aplica decoerência apenas nos rounds intermediários
                self.logger.log(f"Round {round_num + 1}: Decoerência aplicada (round intermediário).")
                self._network.timeslot(Decoherence=True)

        self.logger.log(f"Purificação por bombardeamento concluída com sucesso entre {alice_id} e {bob_id}, a fidelidade final é {eprs[0].get_current_fidelity()}.")
        return True
    
    
    # def purification_pumping(self, alice_id: int, bob_id: int, rounds: int) -> bool:
    #         """
    #         Purificação por Bombardeamento (Pumping) de EPRs com verificação de canal e criação conforme necessário.

    #         Args:
    #             alice_id (int): ID do host Alice.
    #             bob_id (int): ID do host Bob.
    #             rounds (int): Número de rounds de purificação.

    #         Returns:
    #             bool: True se a purificação foi bem-sucedida, False caso contrário.
    #         """
            
    #         # Verifica o nível de ruído do canal
    #         channel_info = self._network.get_channel_info(alice_id, bob_id)
    #         # if any(channel_info.get(f'prob_erro_{tipo}', 0.0) > 0.2 for tipo in ['X', 'Y', 'Z', 'XZ']):
    #         #     self.logger.log(f"Purificação abortada: Canal entre {alice_id} e {bob_id} é muito ruidoso.")
    #         #     return False
            
    #         self.logger.log(f"Iniciando purificação por bombardeamento entre {alice_id} e {bob_id} para {rounds} rounds.")
            
    #         eprs = self._network.get_eprs_from_edge(alice_id, bob_id)
    #         new_epr = None
            
    #         for round_num in range(rounds):
    #             self.logger.log(f"Timeslot {self._network.get_timeslot()}: Executando round {round_num + 1} de purificação por bombardeamento.")
                
    #             if len(eprs) < 2:
    #                 # Se não houver EPRs suficientes, cria novos
    #                 missing_eprs = 2 - len(eprs)
    #                 self.logger.log(f"Timeslot: {self._network.get_timeslot()} Faltam {missing_eprs} EPRs para o round {round_num + 1}. Criando mais EPRs...")
    #                 for _ in range(missing_eprs):
    #                     new_base_epr = self._physical_layer.create_epr_pair(increment_timeslot=False)
    #                     self._physical_layer.add_epr_to_channel(new_base_epr, (alice_id, bob_id))
    #                     self.eprs_pairs_created += 1
    #                 eprs = self._network.get_eprs_from_edge(alice_id, bob_id)

    #             # Seleção dos EPRs baseados no round atual
    #             if round_num == 0:
    #                 # No primeiro round, cria e pega dois EPRs base para purificação
    #                 epr1 = eprs[-2] if len(eprs) > 1 else self._physical_layer.create_epr_pair(increment_timeslot=False)
    #                 epr2 = eprs[-1] if len(eprs) > 0 else self._physical_layer.create_epr_pair(increment_timeslot=False)
    #                 self.logger.log(f"Round {round_num + 1}: Pegando dois EPRs base para purificação: f_base1 (fidelidade {epr1.get_current_fidelity()}) e f_base2 (fidelidade {epr2.get_current_fidelity()}).")
    #             elif round_num == 1:
    #                 # No segundo round, usa o EPR purificado e cria outro EPR base
    #                 epr1 = new_epr  # f'
    #                 epr2 = self._physical_layer.create_epr_pair(increment_timeslot=False)  # Novo EPR base
    #                 self.logger.log(f"Round {round_num + 1}: Pegando EPR purificado f' (fidelidade {epr1.get_current_fidelity()}) e criando novo EPR base (fidelidade {epr2.get_current_fidelity()}).")
    #             else:
    #                 # Nos rounds subsequentes, usa o EPR purificado e outro EPR base do canal
    #                 epr1 = new_epr  # f''
    #                 epr2 = self._physical_layer.create_epr_pair(increment_timeslot=False)  # Novo EPR base
    #                 self.logger.log(f"Round {round_num + 1}: Pegando EPR purificado f'' (fidelidade {epr1.get_current_fidelity()}) e criando novo EPR base (fidelidade {epr2.get_current_fidelity()}).")

    #             # Fidelidades dos dois EPRs
    #             f1 = epr1.get_current_fidelity()
    #             f2 = epr2.get_current_fidelity()
    #             self.logger.log(f"Purificando par de EPRs: fidelidades {f1} e {f2}.")
                
    #             # Determina a probabilidade de sucesso
    #             canal_tipo = channel_info.get('type', 'desconhecido')
    #             success = False
    #             new_fidelity = None
                
    #             if canal_tipo in ['X', 'Z', 'Y']:
    #                 p_success = (f1 * f2) + (1 - f1) * (1 - f2)
    #                 x = random.uniform(0, 1)
    #                 if p_success >= x:
    #                     new_fidelity = f1 * f2 / (f1 * f2 + (1 - f1) * (1 - f2))
    #                     success = True
    #                     self.logger.log(f"Round {round_num + 1} - Sucesso: Probabilidade {p_success}, Nova Fidelidade: {new_fidelity}")
    #                 else:
    #                     self.logger.log(f"Round {round_num + 1} - Falha: Probabilidade {p_success}.")
    #                     self.last_error = "Erro de probabilidade de sucesso."

    #             elif canal_tipo == 'XZ':
    #                 p_success = ((f1 + (1 - f1) / 3) * (f2 + (1 - f2) / 3) + (2 * (1 - f1) / 3) * (2 * (1 - f2) / 3))
    #                 x = random.uniform(0, 1)
    #                 if p_success >= x:
    #                     new_fidelity = (1 / p_success) * (f1 * f2 + ((1 - f1) / 3) * ((1 - f2) / 3))
    #                     success = True
    #                     self.logger.log(f"Round {round_num + 1} - Sucesso: Probabilidade {p_success}, Nova Fidelidade: {new_fidelity}")
    #                 else:
    #                     self.logger.log(f"Round {round_num + 1} - Falha: Probabilidade {p_success}.")
    #                     self.last_error = "Erro de probabilidade de sucesso."
    #             else:
    #                 self.logger.log(f"Tipo de canal desconhecido '{canal_tipo}'. Purificação falhou.")
    #                 self.last_error = "Tipo de canal desconhecido."
    #                 success = False

    #             self.eprs_pairs_consumed += 2
    #             # Remove os EPRs usados do canal, independentemente do sucesso
    #             self._physical_layer.remove_epr_from_channel([epr1, epr2], (alice_id, bob_id))

    #             if success:
    #                 # Adiciona o novo EPR purificado ao canal
    #                 new_epr = self._physical_layer.create_epr_pair(fidelity=new_fidelity, increment_timeslot=False)
    #                 self._physical_layer.add_epr_to_channel(new_epr, (alice_id, bob_id))
    #                 eprs = self._network.get_eprs_from_edge(alice_id, bob_id)
    #                 self.created_eprs.append(new_epr)  # Adiciona o EPR purificado à lista de EPRs criados
                    
    #             else:
    #                 self.logger.log(f"Round {round_num + 1}: Purificação falhou. EPRs removidos do canal.")
    #                 self.last_error = "Erro de probabilidade de sucesso."
    #                 return False
                
    #             if round_num == 0:
    #                 # Nunca aplica decoerência no primeiro round
    #                 self.logger.log(f"Round {round_num + 1}: Decoerência não aplicada (primeiro round).")
    #                 self._network.timeslot(Decoherence=False)
    #             elif round_num == rounds - 1:
    #                 # Não aplica decoerência no último round
    #                 self.logger.log(f"Round {round_num + 1}: Decoerência não aplicada (último round).")
    #                 self._network.timeslot(Decoherence=False)
    #             else:
    #                 # Aplica decoerência apenas nos rounds intermediários
    #                 self.logger.log(f"Round {round_num + 1}: Decoerência aplicada (round intermediário).")
    #                 self._network.timeslot(Decoherence=True)
                    
    #         self.logger.log(f"Purificação por bombardeamento concluída com sucesso entre {alice_id} e {bob_id}.")
    #         return True



    def round_estimates(self, alice_id: int, bob_id: int, target_fidelity: float = 1.0, purification_type: str = None):
        """
        Estima o número de rounds e EPRs necessários para atingir a fidelidade alvo.
        
        Args:
            alice_id (int): ID do host Alice.
            bob_id (int): ID do host Bob.
            purification_type (str): Tipo de purificação ("symmetric" ou "pumping").
            target_fidelity (float): Fidelidade alvo desejada.
            
        Returns:
            dict: Dicionário com a estimativa de rounds, EPRs base necessários e fidelidade final.
        """
        MAX_ROUNDS = 1000
        MIN_INCREMENT = 0.001  # Incremento mínimo de fidelidade para continuar
        created_temp_epr = False  # Flag para verificar se criamos um par EPR temporário

        # Obter a fidelidade inicial e o tipo de canal
        channel_info = self._network.get_channel_info(alice_id, bob_id)
        canal_tipo = channel_info.get('type', 'desconhecido')

        # Obtém os pares EPR existentes entre Alice e Bob
        epr_pairs = self._network.get_eprs_from_edge(alice_id, bob_id)

        if not epr_pairs:
            # Não há pares EPR, então cria um para medir a fidelidade
            self.logger.log(f"Não há pares EPR entre {alice_id} e {bob_id}. Criando um par EPR temporário para medir a fidelidade.")
            try:
                temp_epr = self._physical_layer.create_epr_pair(increment_timeslot=False)
                self._physical_layer.add_epr_to_channel(temp_epr, (alice_id, bob_id))
                created_temp_epr = True  # Flag indicando que criamos um par temporário
                initial_fidelity = temp_epr.get_current_fidelity()
                self.logger.log(f"Fidelidade inicial do par EPR temporário: {initial_fidelity}")
            except Exception as e:
                self.logger.log(f"Erro ao criar ou medir o par EPR temporário: {e}")
                return {}
        else:
            # Fidelidade inicial do último par EPR existente
            try:
                initial_fidelity = epr_pairs[0].get_current_fidelity()
            except IndexError:
                self.logger.log(f"Erro ao acessar a fidelidade inicial: Lista de EPRs está vazia.")
                return {}

        # Se a fidelidade inicial já é suficiente
        if initial_fidelity >= target_fidelity:
            if created_temp_epr:
                # Remove o par EPR temporário se foi criado
                self._physical_layer.remove_epr_from_channel([temp_epr], (alice_id, bob_id))
                self.logger.log(f"Par EPR temporário removido após verificação.")
            return {
                "symmetric": {"rounds": 0, "required_eprs": 0, "final_fidelity": initial_fidelity},
                "pumping": {"rounds": 0, "required_eprs": 0, "final_fidelity": initial_fidelity},
                "canal_tipo": canal_tipo
            }

        def calculate_for_type(purification_type):
            rounds = 0
            current_fidelity = initial_fidelity
            required_eprs_base = 0  # Total de EPRs base necessários

            while current_fidelity < target_fidelity and rounds < MAX_ROUNDS:
                rounds += 1

                # Calcula o número de EPRs base necessários
                if purification_type == "symmetric":
                    num_eprs_base_needed = 2 ** rounds
                elif purification_type == "pumping":
                    num_eprs_base_needed = 2 if rounds == 1 else 1
                else:
                    raise ValueError(f"Tipo de purificação '{purification_type}' não identificado.")

                required_eprs_base += num_eprs_base_needed

                # Fidelidade antes do round
                fidelity_before = current_fidelity

                # Processo de purificação
                f1, f2 = current_fidelity, current_fidelity
                p_success = ((f1 + (1 - f1) / 3) * (f2 + (1 - f2) / 3) + (2 * (1 - f1) / 3) * (2 * (1 - f2) / 3))
                new_fidelity = (1 / p_success) * (f1 * f2 + ((1 - f1) / 3) * ((1 - f2) / 3))

                # Atualiza a fidelidade
                fidelity_increment = new_fidelity - current_fidelity
                current_fidelity = new_fidelity

                self.logger.log(f"Round {rounds}: Fidelidade antes {fidelity_before}, Fidelidade após {current_fidelity}, Incremento {fidelity_increment}.")

                # Verifica se o incremento é menor que o mínimo aceitável
                if fidelity_increment < MIN_INCREMENT:
                    self.logger.log(f"Purificação interrompida: Incremento de fidelidade muito pequeno ({fidelity_increment}).")
                    break

            return {
                "rounds": rounds,
                "required_eprs": required_eprs_base,
                "final_fidelity": current_fidelity
            }

        # Calcula para os tipos de purificação
        results = {}
        if purification_type is None:
            results = {
                "symmetric": calculate_for_type("symmetric"),
                "pumping": calculate_for_type("pumping"),
            }
        else:
            results = {
                purification_type: calculate_for_type(purification_type)
            }

        # Remove o par EPR temporário, se criado
        if created_temp_epr:
            self._physical_layer.remove_epr_from_channel([temp_epr], (alice_id, bob_id))
            self.logger.log(f"Par EPR temporário removido após cálculo de estimativas.")

        results["canal_tipo"] = canal_tipo
        return results
