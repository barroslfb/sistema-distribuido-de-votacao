import unittest
from unittest.mock import patch

from src.voting import Voting


class VotingTests(unittest.TestCase):
    def test_inicia_com_as_tres_opcoes_e_estado_nao_iniciado(self):
        voting = Voting(10)

        self.assertEqual(voting.votos, {"A": 0, "B": 0, "C": 0})
        self.assertEqual(voting.verificar_estado(), "não iniciada")

    def test_rejeita_duracao_invalida(self):
        for duration in (0, -1, float("inf"), float("nan")):
            with self.subTest(duration=duration):
                with self.assertRaises(ValueError):
                    Voting(duration)

        for duration in ("10", None, True):
            with self.subTest(duration=duration):
                with self.assertRaises(TypeError):
                    Voting(duration)

    def test_prazo_encerra_votacao_sem_bloquear_inicio(self):
        voting = Voting(10)
        with patch("src.voting.time.monotonic", side_effect=[100, 109, 110]):
            voting.iniciar_votacao()

            self.assertEqual(voting.verificar_estado(), "votando")
            self.assertEqual(voting.verificar_estado(), "encerrada")

    def test_rejeita_votos_fora_do_periodo_ativo(self):
        voting = Voting(10)
        with self.assertRaises(RuntimeError):
            voting.registro_voto("A", "ana")

        with patch("src.voting.time.monotonic", side_effect=[100, 100, 110]):
            voting.iniciar_votacao()
            voting.registro_voto("A", "ana")

            with self.assertRaises(RuntimeError):
                voting.registro_voto("B", "bia")

        self.assertEqual(voting.votos, {"A": 1, "B": 0, "C": 0})

    def test_encerramento_explicito_e_inicio_unico(self):
        voting = Voting(10)
        with patch("src.voting.time.monotonic", return_value=100):
            voting.iniciar_votacao()
            with self.assertRaises(RuntimeError):
                voting.iniciar_votacao()

        voting.encerrar_votacao()
        self.assertEqual(voting.verificar_estado(), "encerrada")
        with self.assertRaises(RuntimeError):
            voting.iniciar_votacao()


if __name__ == "__main__":
    unittest.main()
