"""Rangos y precios pegados: pruebas sin Tk, ventanas, navegador ni conexión."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.test_price_changes import app, fixture, Var, Widget


class PasteTable(Widget):
    def __init__(self):
        super().__init__()
        self.rows = {}
        self.selected = ()
    def selection(self): return self.selected
    def selection_set(self, items): self.selected = tuple(items)
    def get_children(self): return tuple(self.rows)
    def delete(self, *ids):
        for item in ids: self.rows.pop(item)
    def insert(self, *args, iid, values, tags): self.rows[iid] = (values, tags)
    def identify_row(self, y): return str(y) if str(y) in self.rows else ""


def paste_view(rows):
    view = fixture()
    view._campos_editor_precios = [Widget() for _ in range(7)]
    view._bloques_editor_precios = [Widget() for _ in range(3)]
    view.btn_pegar_precios = Widget()
    view.btn_segundo_rango = Widget()
    view.tabla_pegado_precios = PasteTable()
    view._columnas_tabla_pegado = ("Barra", "RangoInicial1", "RangoFinal1", "Precio1", "RangoInicial2", "RangoFinal2", "Precio2")
    view.lbl_vacio_pegado = Widget()
    view._editor_precios_vars = [Var(value) for value in ("", "1", "1000", "", "", "", "")]
    view._editor_precios_entries = [Widget() for _ in range(7)]
    view.lbl_error_editor_precios = Widget()
    view.btn_guardar_fila_precios = Widget()
    view.btn_cancelar_fila_precios = Widget()
    view._escribir_tabla_precios(rows)
    return view


class PriceRangePasteTests(unittest.TestCase):
    def test_rangos_unitarios_decimales_y_limites(self):
        for text, expected in (('1', '1'), ('1000', '1000'), ('0,001', '0.001'), ('2.500', '2.5')):
            with self.subTest(text=text):
                self.assertEqual(app.normalizar_cantidad_rango(text), expected)
        for text in ('', '0', '-1', '1001', '1 - 2', 'NaN', 'mil', '1,2.3'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                app.normalizar_cantidad_rango(text)

    def test_pegado_excel_conserva_barras_y_tres_formatos(self):
        for text, width in (('Barra interna\tPrecio\n00123\t1290', 2),
                ('Barra\tRangoInicial1\tRangoFinal1\tPrecio1\n00123\t1\t1000\t1290', 4),
                ('Código\tRangoInicial1\tRangoFinal1\tPrecio1\tRangoInicial2\tRangoFinal2\tPrecio2\n00123\t1\t2\t1290\t3\t1000\t990', 7)):
            rows = app.parsear_tabla_precios(text)
            self.assertEqual(len(rows[0]), width)
            self.assertEqual(rows[0][0], '00123')
        for text in ('', '00123', '00123\t1\t2', '00123\t1\t2\t3\t4\t5'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                app.parsear_tabla_precios(text)

    def test_dos_rangos_habilitan_siete_campos_y_respetan_los_precios(self):
        view = paste_view([['00123', '1', '2', '1290', '3', '1000', '990']])
        self.assertTrue(view.ingresar_rangos.get())
        self.assertTrue(view.enable_r2.get())
        self.assertIn('7 columnas', view.btn_pegar_precios.options['text'])
        self.assertTrue(view._bloques_editor_precios[2].visible)
        self.assertTrue(view._actualizar_pegado_precios())
        view._build_preview_from_paste()
        row = view.tree.rows['0']
        self.assertEqual([row[c] for c in ('RangoInicial1','RangoFinal1','Precio1','RangoInicial2','RangoFinal2','Precio2')],
                         ['1','2','1290','3','1000','990'])

    def test_compatibilidad_de_dos_columnas_y_rango_por_defecto(self):
        view = paste_view([['00123', '1990']])
        self.assertFalse(view.ingresar_rangos.get())
        self.assertFalse(view.enable_r2.get())
        self.assertTrue(view._actualizar_pegado_precios())
        view._build_preview_from_paste()
        row = view.tree.rows['0']
        self.assertEqual((row['RangoInicial1'],row['RangoFinal1'],row['Precio1']), ('1','1000','1990'))

    def test_activar_segundo_rango_activa_primero_y_precio_sin_borrar_textos(self):
        view = paste_view([['00123', '1', '2', '1290', '3', '1000', '990']])
        view.ingresar_rangos.set(False)
        view._cambiar_ingreso_rangos()
        self.assertFalse(view.enable_r2.get())
        self.assertFalse(view._bloques_editor_precios[2].visible)
        self.assertEqual(view._filas_pegado_precios[0][6], '990')
        view.enable_r2.set(True)
        view._toggle_r2()
        self.assertTrue(view.ingresar_rangos.get())
        self.assertEqual(view._filas_pegado_precios[0][4], '3')
        self.assertEqual(view._filas_pegado_precios[0][5], '1000')
        self.assertIn('7 columnas', view.btn_pegar_precios.options['text'])

    def test_columna_de_rango_vacia_no_desplaza_filas(self):
        view = paste_view([['00123','1','2','1290'], ['00456','','1000','1990'], ['00789','3','1000','990']])
        self.assertFalse(view._actualizar_pegado_precios())
        self.assertIn('Fila 2', view.lbl_pegado_precios.options['text'])
        self.assertEqual(view._read_pasted_lists(), (['00123','00456','00789'], ['1290','1990','990']))
        self.assertIn(1, view._problemas_pegado_precios[2])

    def test_rango_sin_barra_marca_fila(self):
        view = paste_view([['','1','2','1290']])
        self.assertFalse(view._actualizar_pegado_precios())
        self.assertIn('falta barra', view.lbl_pegado_precios.options['text'])

    def test_rango_dos_incompleto_o_superpuesto_no_permite_continuar(self):
        for initial2, final2, price2 in (('3','1000',''), ('','','990'), ('2','1000','990'), ('4','3','990'), ('3','','990')):
            view = paste_view([['00123','1','2','1290',initial2,final2,price2]])
            with self.subTest(initial2=initial2, final2=final2, price2=price2):
                self.assertFalse(view._actualizar_pegado_precios())
                self.assertEqual(view.btn_revisar_precios.options['state'], 'disabled')

    def test_segundo_rango_opcional_por_producto(self):
        view = paste_view([['00123','1','2','1290','3','1000','990'], ['00456','1','1000','2990','','','']])
        self.assertTrue(view._actualizar_pegado_precios())
        view._build_preview_from_paste()
        self.assertEqual(view.tree.rows['1']['Precio2'], '')
        self.assertEqual(view.tree.rows['1']['RangoInicial2'], '')

    def test_rangos_decimales_no_se_limpian_como_un_precio(self):
        view = paste_view([['00123','0,001','0,999','1.290','1','1000','990']])
        view._build_preview_from_paste()
        row = view.tree.rows['0']
        self.assertEqual(row['RangoInicial1'], '0.001')
        self.assertEqual(row['RangoFinal1'], '0.999')
        self.assertEqual(row['Precio1'], '1290')

    def test_exporta_siete_columnas_con_ambos_rangos(self):
        view = paste_view([['00123','1','2','1290','3','1000','990']])
        view._build_preview_from_paste()
        view.export_only_valid = Var(True)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'precios.xlsx'
            with mock.patch.object(app.filedialog, 'asksaveasfilename', return_value=str(path)), mock.patch.object(app.messagebox, 'showinfo'):
                view._export()
            output = app.pd.read_excel(path, dtype=str).fillna('')
        self.assertEqual(output.columns.tolist(), ['Código','RangoInicial1','RangoFinal1','Precio1','RangoInicial2','RangoFinal2','Precio2'])
        self.assertEqual(output.iloc[0].tolist(), ['A022766','1','2','1290','3','1000','990'])

    def test_desactivar_segundo_rango_excluye_datos_ocultos_del_excel(self):
        view = paste_view([['00123','1','2','1290','3','1000','990']])
        view._build_preview_from_paste()
        view.enable_r2.set(False)
        view._toggle_r2()
        view.export_only_valid = Var(True)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'precios.xlsx'
            with mock.patch.object(app.filedialog, 'asksaveasfilename', return_value=str(path)), mock.patch.object(app.messagebox, 'showinfo'):
                view._export()
            output = app.pd.read_excel(path, dtype=str).fillna('')
        self.assertEqual(output.iloc[0][['RangoInicial2','RangoFinal2','Precio2']].tolist(), ['', '', ''])
        self.assertEqual(view._filas_pegado_precios[0][6], '990')

    def test_edicion_de_tabla_con_rangos_cruzados_impide_exportar(self):
        view = paste_view([['00123','1','2','1290','3','1000','990']])
        view._build_preview_from_paste()
        view.tree.set('0','RangoInicial2','2')
        view.export_only_valid = Var(True)
        with mock.patch.object(app.filedialog, 'asksaveasfilename') as save, mock.patch.object(app.messagebox, 'showwarning') as warning:
            view._export()
            save.assert_not_called()
            self.assertIn('después', warning.call_args.args[1])

    def test_revisar_varias_veces_no_pierde_rangos(self):
        view = paste_view([['00123','1','2','1290','3','1000','990']])
        view._build_preview_from_paste()
        first = dict(view.tree.rows['0'])
        view._build_preview_from_paste()
        self.assertEqual(view.tree.rows['0'], first)

    def test_limpiar_borra_las_siete_columnas_y_la_practica(self):
        view = paste_view([['00123','1','2','1290','3','1000','990']])
        view._modo_ejemplo_precios = True
        view._limpiar_pegado_precios()
        self.assertFalse(view._modo_ejemplo_precios)
        self.assertEqual(view._filas_pegado_precios, [])

    def test_segundo_rango_se_muestra_sin_abrir_opciones_avanzadas(self):
        view = paste_view([['00123','1','2','1290','3','1000','990']])
        view.var_opciones_rangos = Var(False)
        view.side_shell_rangos = Widget()
        app.TivendoWindow._toggle_opciones_rangos(view)
        columns = view.tree.options['displaycolumns']
        self.assertEqual(columns[3:9], ['RangoInicial1','RangoFinal1','Precio1','RangoInicial2','RangoFinal2','Precio2'])

    def test_rango_inicial_y_final_incompletos_marcan_su_propio_campo(self):
        for initial, final, attribute in (('', '1000', 'txt_ri1'), ('1', '', 'txt_rf1'), ('3', '2', 'txt_rf1')):
            view = paste_view([['00123', initial, final, '1290']])
            with self.subTest(initial=initial, final=final):
                self.assertFalse(view._actualizar_pegado_precios())
                self.assertIn(1 if attribute == 'txt_ri1' else 2, view._problemas_pegado_precios[1])

    def test_un_rango_usa_cuatro_columnas_y_oculta_el_segundo_bloque(self):
        view = paste_view([['00123','1','1000','1290']])
        self.assertIn('4 columnas', view.btn_pegar_precios.options['text'])
        self.assertFalse(view._bloques_editor_precios[2].visible)
        self.assertTrue(view._campos_editor_precios[1].visible)
        self.assertTrue(view._campos_editor_precios[2].visible)

    def test_ejemplo_con_las_cantidades_de_tivendo_es_practica(self):
        view = paste_view([['00123','1','1','590','2','3','450']])
        view._filas_pegado_precios = []
        view._ejemplo_precios()
        self.assertTrue(view._modo_ejemplo_precios)
        self.assertEqual(view._filas_pegado_precios[0], ['00123','1','1','590','2','3','450'])
        with mock.patch.object(app.filedialog, 'asksaveasfilename') as save, mock.patch.object(app.messagebox, 'showinfo'):
            view._export()
            save.assert_not_called()

    def test_agregar_y_editar_una_fila_desde_los_campos_cortos(self):
        view = paste_view([])
        values = ['00123','1','2','1290','3','1000','990']
        view.enable_r2.set(True)
        for var, value in zip(view._editor_precios_vars, values):
            var.set(value)
        self.assertTrue(view._guardar_fila_pegado())
        self.assertEqual(view._filas_pegado_precios, [values])
        self.assertFalse(view._hay_borrador_precio())
        view.tabla_pegado_precios.selection_set(['0'])
        view._editar_fila_pegado()
        self.assertEqual(view._fila_editor_precios, 0)
        view._editor_precios_vars[3].set('1490')
        self.assertTrue(view._guardar_fila_pegado())
        self.assertEqual(len(view._filas_pegado_precios), 1)
        self.assertEqual(view._filas_pegado_precios[0][3], '1490')

    def test_maximo_1000_se_aplica_a_edicion_pegado_y_exportacion(self):
        view = paste_view([['00123','1','1001','1290']])
        self.assertFalse(view._actualizar_pegado_precios())
        self.assertIn('1000', view.lbl_pegado_precios.options['text'])
        view._filas_pegado_precios[0][2] = '1000'
        view._actualizar_pegado_precios()
        view._build_preview_from_paste()
        view.tree.set('0', 'RangoFinal1', '1001')
        view.export_only_valid = Var(True)
        with mock.patch.object(app.filedialog, 'asksaveasfilename') as save, mock.patch.object(app.messagebox, 'showwarning'):
            view._export()
            save.assert_not_called()
        for var, value in zip(view._editor_precios_vars, ['00123','1','1001','1290','','','']):
            var.set(value)
        self.assertFalse(view._guardar_fila_pegado())
        self.assertIn('1000', view.lbl_error_editor_precios.options['text'])

    def test_quitar_varias_filas_no_quita_otras(self):
        view = paste_view([['00123','1290'], ['00456','1990'], ['00789','2990']])
        view.tabla_pegado_precios.selection_set(['0','2'])
        view._quitar_filas_pegado()
        self.assertEqual(view._filas_pegado_precios, [['00456','','','1990','','','']])

    def test_la_revision_incluye_edicion_pendiente_y_bloquea_borrador_invalido(self):
        view = paste_view([['00123','1','1000','1290']])
        view.tabla_pegado_precios.selection_set(['0'])
        view._editar_fila_pegado()
        view._editor_precios_vars[3].set('1490')
        view._build_preview_from_paste()
        self.assertEqual(view.tree.rows['0']['Precio1'], '1490')
        view._editor_precios_vars[0].set('00999')
        view._editor_precios_vars[3].set('')
        view._show.reset_mock()
        view._build_preview_from_paste()
        view._show.assert_not_called()

    def test_no_se_descarta_edicion_al_cambiar_o_quitar_filas_sin_confirmar(self):
        view = paste_view([['00123','1290'], ['00456','1990']])
        view.tabla_pegado_precios.selection_set(['0'])
        view._editar_fila_pegado()
        view._editor_precios_vars[3].set('1490')
        view.tabla_pegado_precios.selection_set(['1'])
        with mock.patch.object(app.messagebox, 'askyesno', return_value=False):
            view._editar_fila_pegado()
            view._quitar_filas_pegado()
        self.assertEqual(view._fila_editor_precios, 0)
        self.assertEqual(view._editor_precios_vars[3].get(), '1490')
        self.assertEqual(len(view._filas_pegado_precios), 2)


if __name__ == '__main__':
    unittest.main()
