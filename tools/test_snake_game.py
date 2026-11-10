"""Pruebas de Snake sin abrir ventanas."""
import unittest
from unittest import mock

import buscador_codigos as app
from buscador_codigos import InvadersRound, PongRound, SnakeGame


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


class ArcadeGameTests(unittest.TestCase):
    def test_pong_rebota_en_la_pala_y_da_punto_si_sale(self):
        game = PongRound()
        game.x, game.y, game.dx, game.dy = 34, game.player, -4, 0
        game.advance(set())
        self.assertGreater(game.dx, 0)
        self.assertEqual(game.points, [0, 0])
        game.x, game.y, game.dx = -4, 10, -4
        game.advance(set())
        self.assertEqual(game.points, [0, 1])
        self.assertEqual(game.x, game.width / 2)

    def test_space_invaders_puntua_y_pasa_a_la_siguiente_oleada(self):
        game = InvadersRound()
        game.enemies = [(100, 100)]
        game.shots = [(101, 108)]
        self.assertIsNone(game.advance(set()))
        self.assertEqual((game.score, game.wave), (10, 2))
        self.assertGreater(len(game.enemies), 1)
        self.assertEqual(game.shots, [])

    def test_escudos_absorben_disparos_desde_ambos_lados(self):
        game = InvadersRound()
        x, y = min(game.shields)
        other_x, other_y = max(game.shields)
        game.shots = [(x, y + 8)]
        game.enemy_shots = [(other_x, other_y - 4)]

        self.assertIsNone(game.advance(set()))
        self.assertEqual(game.shots, [])
        self.assertEqual(game.enemy_shots, [])
        self.assertNotIn((x, y), game.shields)
        self.assertNotIn((other_x, other_y), game.shields)
        self.assertEqual((game.score, game.lives), (0, 3))

    def test_platillo_cruza_y_otorga_puntos_al_recibir_un_disparo(self):
        game = InvadersRound()
        game.ticks = 319
        game.advance(set())
        self.assertIsNotNone(game.bonus_x)
        starting_x = game.bonus_x
        for _ in range(20):
            game.advance(set())
        self.assertGreater(game.bonus_x, starting_x)
        game.shots = [(game.bonus_x, 30)]

        game.advance(set())
        self.assertEqual(game.score, 50)
        self.assertIsNone(game.bonus_x)
        self.assertEqual(game.shots, [])

    def test_salir_cancela_el_temporizador_de_los_juegos_activos(self):
        for panel_class, timer in ((app.SnakePanel, "_tick_id"), (app.ArcadeActionPanel, "_tick_id"),
                                   (app.MemoryPanel, "_hide_id")):
            with self.subTest(panel=panel_class.__name__), mock.patch.object(app.ttk.Frame, "destroy", autospec=True) as destroy:
                panel = object.__new__(panel_class)
                setattr(panel, timer, "after#1")
                panel.after_cancel = mock.Mock()
                panel.destroy()
                panel.after_cancel.assert_called_once_with("after#1")
                self.assertIsNone(getattr(panel, timer))
                destroy.assert_called_once_with(panel)
