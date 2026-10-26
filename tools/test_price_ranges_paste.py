"""Rangos y precios pegados: pruebas sin Tk, ventanas, navegador ni conexión."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.test_price_changes import app, fixture, Var, Widget


def paste_view(rows):
    view = fixture()
    view._campos_pegado_precios = [Widget() for _ in range(7)]
    view._bloques_pegado_precios = [Widget() for _ in range(3)]
    view._contenedor_pegado = Widget()
    view.btn_pegar_precios = Widget()
    view.lbl_formato_precios = Widget()
    view._escribir_tabla_precios(rows)
    return view


class PriceRangePasteTests(unittest.TestCase):
    def test_rangos_unitarios_decimales_y_limites(self):
        for text, expected in (('1', '1'), ('9999', '9999'), ('0,001', '0.001'), ('2.500', '2.5')):
            with self.subTest(text=text):
                self.assertEqual(app.normalizar_cantidad_rango(text), expected)
        for text in ('', '0', '-1', '1 - 2', 'NaN', 'mil', '1,2.3'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                app.normalizar_cantidad_rango(text)

    def test_pegado_excel_conserva_barras_y_tres_formatos(self):
        for text, width in (('Barra interna\tPrecio\n00123\t1290', 2),
                ('Barra\tRangoInicial1\tRangoFinal1\tPrecio1\n00123\t1\t9999\t1290', 4),
                ('Código\tRangoInicial1\tRangoFinal1\tPrecio1\tRangoInicial2\tRangoFinal2\tPrecio2\n00123\t1\t2\t1290\t3\t9999\t990', 7)):
            rows = app.parsear_tabla_precios(text)
            self.assertEqual(len(rows[0]), width)
            self.assertEqual(rows[0][0], '00123')
        for text in ('', '00123', '00123\t1\t2', '00123\t1\t2\t3\t4\t5'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                app.parsear_tabla_precios(text)

    def test_dos_rangos_habilitan_siete_campos_y_respetan_los_precios(self):
        view = paste_view([['00123', '1', '2', '1290', '3', '9999', '990']])
        self.assertTrue(view.ingresar_rangos.get())
        self.assertTrue(view.enable_r2.get())
        self.assertIn('7 columnas', view.btn_pegar_precios.options['text'])
        self.assertTrue(view._bloques_pegado_precios[2].visible)
        self.assertTrue(view._actualizar_pegado_precios())
        view._build_preview_from_paste()
        row = view.tree.rows['0']
        self.assertEqual([row[c] for c in ('RangoInicial1','RangoFinal1','Precio1','RangoInicial2','RangoFinal2','Precio2')],
                         ['1','2','1290','3','9999','990'])

    def test_compatibilidad_de_dos_columnas_y_rango_por_defecto(self):
        view = paste_view([['00123', '1990']])
        self.assertFalse(view.ingresar_rangos.get())
        self.assertFalse(view.enable_r2.get())
        self.assertTrue(view._actualizar_pegado_precios())
        view._build_preview_from_paste()
        row = view.tree.rows['0']
        self.assertEqual((row['RangoInicial1'],row['RangoFinal1'],row['Precio1']), ('1','9999','1990'))

    def test_activar_segundo_rango_activa_primero_y_precio_sin_borrar_textos(self):
        view = paste_view([['00123', '1', '2', '1290', '3', '9999', '990']])
        view.ingresar_rangos.set(False)
        view._cambiar_ingreso_rangos()
        self.assertFalse(view.enable_r2.get())
        self.assertFalse(view._bloques_pegado_precios[2].visible)
        self.assertEqual(view.txt_prec2.text, '990')
        view.enable_r2.set(True)
        view._toggle_r2()
        self.assertTrue(view.ingresar_rangos.get())
        self.assertEqual(view.txt_ri2.text, '3')
        self.assertEqual(view.txt_rf2.text, '9999')
        self.assertIn('7 columnas', view.btn_pegar_precios.options['text'])

    def test_columna_de_rango_vacia_no_desplaza_filas(self):
        view = paste_view([['00123','1','2','1290'], ['00456','','9999','1990'], ['00789','3','9999','990']])
        self.assertFalse(view._actualizar_pegado_precios())
        self.assertIn('Fila 2', view.lbl_pegado_precios.options['text'])
        self.assertEqual(view._read_pasted_lists(), (['00123','00456','00789'], ['1290','1990','990']))
        self.assertEqual(view.txt_ri1.errors[0][1], '2.0')

    def test_rango_sin_barra_marca_fila(self):
        view = paste_view([['','1','2','1290']])
        self.assertFalse(view._actualizar_pegado_precios())
        self.assertIn('falta barra', view.lbl_pegado_precios.options['text'])

    def test_rango_dos_incompleto_o_superpuesto_no_permite_continuar(self):
        for initial2, final2, price2 in (('3','9999',''), ('','','990'), ('2','9999','990'), ('4','3','990'), ('3','','990')):
            view = paste_view([['00123','1','2','1290',initial2,final2,price2]])
            with self.subTest(initial2=initial2, final2=final2, price2=price2):
                self.assertFalse(view._actualizar_pegado_precios())
                self.assertEqual(view.btn_revisar_precios.options['state'], 'disabled')

    def test_segundo_rango_opcional_por_producto(self):
        view = paste_view([['00123','1','2','1290','3','9999','990'], ['00456','1','9999','2990','','','']])
        self.assertTrue(view._actualizar_pegado_precios())
        view._build_preview_from_paste()
        self.assertEqual(view.tree.rows['1']['Precio2'], '')
        self.assertEqual(view.tree.rows['1']['RangoInicial2'], '')

    def test_rangos_decimales_no_se_limpian_como_un_precio(self):
        view = paste_view([['00123','0,001','0,999','1.290','1','9999','990']])
        view._build_preview_from_paste()
        row = view.tree.rows['0']
        self.assertEqual(row['RangoInicial1'], '0.001')
        self.assertEqual(row['RangoFinal1'], '0.999')
        self.assertEqual(row['Precio1'], '1290')

    def test_exporta_siete_columnas_con_ambos_rangos(self):
        view = paste_view([['00123','1','2','1290','3','9999','990']])
        view._build_preview_from_paste()
        view.export_only_valid = Var(True)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'precios.xlsx'
            with mock.patch.object(app.filedialog, 'asksaveasfilename', return_value=str(path)), mock.patch.object(app.messagebox, 'showinfo'):
                view._export()
            output = app.pd.read_excel(path, dtype=str).fillna('')
        self.assertEqual(output.columns.tolist(), ['Código','RangoInicial1','RangoFinal1','Precio1','RangoInicial2','RangoFinal2','Precio2'])
        self.assertEqual(output.iloc[0].tolist(), ['A022766','1','2','1290','3','9999','990'])

    def test_desactivar_segundo_rango_excluye_datos_ocultos_del_excel(self):
        view = paste_view([['00123','1','2','1290','3','9999','990']])
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
        self.assertEqual(view.txt_prec2.text, '990')

    def test_edicion_de_tabla_con_rangos_cruzados_impide_exportar(self):
        view = paste_view([['00123','1','2','1290','3','9999','990']])
        view._build_preview_from_paste()
        view.tree.set('0','RangoInicial2','2')
        view.export_only_valid = Var(True)
        with mock.patch.object(app.filedialog, 'asksaveasfilename') as save, mock.patch.object(app.messagebox, 'showwarning') as warning:
            view._export()
            save.assert_not_called()
            self.assertIn('después', warning.call_args.args[1])

    def test_revisar_varias_veces_no_pierde_rangos(self):
        view = paste_view([['00123','1','2','1290','3','9999','990']])
        view._build_preview_from_paste()
        first = dict(view.tree.rows['0'])
        view._build_preview_from_paste()
        self.assertEqual(view.tree.rows['0'], first)

    def test_limpiar_borra_las_siete_columnas_y_la_practica(self):
        view = paste_view([['00123','1','2','1290','3','9999','990']])
        view._modo_ejemplo_precios = True
        view._limpiar_pegado_precios()
        self.assertFalse(view._modo_ejemplo_precios)
        self.assertTrue(all(widget.text == '' for widget in view._textos_precios()))

    def test_segundo_rango_se_muestra_sin_abrir_opciones_avanzadas(self):
        view = paste_view([['00123','1','2','1290','3','9999','990']])
        view.var_opciones_rangos = Var(False)
        view.side_shell_rangos = Widget()
        app.TivendoWindow._toggle_opciones_rangos(view)
        columns = view.tree.options['displaycolumns']
        self.assertEqual(columns[3:9], ['RangoInicial1','RangoFinal1','Precio1','RangoInicial2','RangoFinal2','Precio2'])

    def test_rango_inicial_y_final_incompletos_marcan_su_propio_campo(self):
        for initial, final, attribute in (('', '9999', 'txt_ri1'), ('1', '', 'txt_rf1'), ('3', '2', 'txt_rf1')):
            view = paste_view([['00123', initial, final, '1290']])
            with self.subTest(initial=initial, final=final):
                self.assertFalse(view._actualizar_pegado_precios())
                self.assertTrue(getattr(view, attribute).errors)

    def test_un_rango_usa_cuatro_columnas_y_oculta_el_segundo_bloque(self):
        view = paste_view([['00123','1','9999','1290']])
        self.assertIn('4 columnas', view.btn_pegar_precios.options['text'])
        self.assertFalse(view._bloques_pegado_precios[2].visible)
        self.assertTrue(view._campos_pegado_precios[1].visible)
        self.assertTrue(view._campos_pegado_precios[2].visible)

    def test_ejemplo_con_las_cantidades_de_tivendo_es_practica(self):
        view = paste_view([['00123','1','1','590','2','3','450']])
        for widget in view._textos_precios():
            widget.delete('1.0', 'end')
        view._ejemplo_precios()
        self.assertTrue(view._modo_ejemplo_precios)
        self.assertEqual([widget.text for widget in view._textos_precios()], ['00123','1','1','590','2','3','450'])
        with mock.patch.object(app.filedialog, 'asksaveasfilename') as save, mock.patch.object(app.messagebox, 'showinfo'):
            view._export()
            save.assert_not_called()


if __name__ == '__main__':
    unittest.main()
