import unittest
from unittest.mock import patch

from src.voting import Voting


class VotingTests(unittest.TestCase):
    def test_voto_valido_e_invalidos_ou_duplicados_sem_alteracao(self):
        voting = Voting(10)
        with patch("src.voting.time.monotonic", return_value=100):
            voting.iniciar_votacao()
            with self.assertRaises(ValueError):
                voting.registro_voto("D", "ana")
            voting.registro_voto("A", "ana")
            with self.assertRaises(ValueError):
                voting.registro_voto("B", "ana")

        self.assertEqual(voting.obter_resultados(), {"A": 1, "B": 0, "C": 0})

    def test_prazo_encerra_votacao_e_rejeita_novos_votos(self):
        voting = Voting(10)
        with patch("src.voting.time.monotonic", side_effect=[100, 100, 110]):
            voting.iniciar_votacao()
            voting.registro_voto("C", "ana")
            with self.assertRaises(RuntimeError):
                voting.registro_voto("A", "bia")

        self.assertEqual(voting.obter_resultados(), {"A": 0, "B": 0, "C": 1})


if __name__ == "__main__":
    unittest.main()
