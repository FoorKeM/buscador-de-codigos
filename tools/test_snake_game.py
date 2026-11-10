"""Pruebas de Snake sin abrir ventanas."""
import unittest

from buscador_codigos import SnakeGame


class SnakeGameTests(unittest.TestCase):
    def test_comer_hace_crecer_y_coloca_la_siguiente_comida_en_una_celda_libre(self):
        game = SnakeGame()
        x, y = game.body[0]
        game.food = (x + 1, y)
        self.assertTrue(game.step())
        self.assertEqual(game.body[0], (x + 1, y))
        self.assertEqual(game.score, 1)
        self.assertNotIn(game.food, game.body)

    def test_no_puede_girar_en_u_ni_aceptar_dos_giros_en_el_mismo_paso(self):
        game = SnakeGame()
        x, y = game.body[0]
        game.turn((-1, 0))
        game.turn((0, -1))
        game.turn((-1, 0))
        self.assertTrue(game.step())
        self.assertEqual(game.body[0], (x, y - 1))

    def test_detecta_el_borde_y_el_cuerpo_pero_deja_pasar_por_la_cola_que_sale(self):
        game = SnakeGame()
        game.food = (8, 8)
        game.body = [(game.columns - 1, 4), (game.columns - 2, 4), (game.columns - 3, 4)]
        self.assertFalse(game.step())

        game.body = [(1, 1), (1, 2), (2, 2), (2, 1), (2, 0)]
        self.assertFalse(game.step())
        game.body.pop()
        self.assertTrue(game.step())
        self.assertEqual(game.body[0], (2, 1))

    def test_la_ultima_comida_completa_el_tablero(self):
        game = SnakeGame()
        game.columns, game.rows = 2, 2
        game.body = [(0, 0), (0, 1), (1, 1)]
        game.food = (1, 0)
        self.assertTrue(game.step())
        self.assertIsNone(game.food)
        self.assertEqual(len(game.body), 4)
