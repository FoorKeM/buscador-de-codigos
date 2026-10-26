"""Cambios masivos sin consulta de precios ni descargas al entrar. Sin ventanas."""
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import buscador_codigos as app

REPORT='''<table><tr><td>Código artículo</td><td>Rango 1</td><td>Precio Unitario 1</td><td>Rango 2</td><td>Precio Unitario 2</td></tr>
<tr><td>A022766</td><td>(1 - 9,999)</td><td>1,290</td><td>(10 - 999)</td><td>990</td></tr></table>'''

COLS=('Código','Nombre','CodigoBarraInterno','Precio1','RangoInicial1','RangoFinal1','Precio2','RangoInicial2','RangoFinal2','RangoExistente')
class Widget:
    def __init__(self):self.options={}; self.master=mock.Mock(); self.visible=True
    def config(self,**kw):self.options.update(kw)
    configure=config
    def pack(self,**kw):self.visible=True
    def pack_forget(self):self.visible=False
    def start(self,*a):pass
    def stop(self):pass
    def grid(self,**kw):self.visible=True
    def grid_remove(self):self.visible=False
    def columnconfigure(self,*a,**kw):pass
    def place(self,**kw):self.visible=True
    def place_forget(self):self.visible=False
    def focus_set(self):pass
class Var:
    def __init__(self, value): self.value=value
    def get(self): return self.value
    def set(self, value): self.value=value
class Text:
    def __init__(self, text=''): self.text=text; self.errors=[]
    def get(self,*a): return self.text
    def delete(self,*a): self.text=''
    def insert(self,index,text): self.text=text
    def tag_remove(self,*a): self.errors=[]
    def tag_add(self,*a): self.errors.append(a)
class Tree(Widget):
    def __init__(self):super().__init__();self.rows={}
    def get_children(self):return tuple(self.rows)
    def delete(self,*ids):
        for i in ids:self.rows.pop(i)
    def insert(self,*a,values,tags):self.rows[str(len(self.rows))]=dict(zip(COLS,values))
    def set(self,row,col,*value):
        if value:self.rows[row][col]=value[0]
        return self.rows[row][col]
def fixture():
    view=object.__new__(app.TivendoWindow)
    class NoPrices:
        @property
        def ranges_index(self):raise AssertionError('No consultar precios ni rangos guardados')
    view.master=NoPrices()
    view.df_map=app.pd.DataFrame({'Identificador':['A022766'],'CodigoBarraInterno':['00123'],'Nombre':['PALMERITAS']})
    view.df_view=None
    view.df_preview=None
    view._listado_cargando=False
    view._rangos_index={'A022766':{'rango1':'(1 - 1)','rango2':'(2 - 100)'}}
    view._rangos_fuente='Archivo de prueba'
    view._listado_load_job=0
    view._modo_ejemplo_precios=False
    view.ingresar_rangos=Var(False)
    view.enable_r2=Var(False)
    view._filas_pegado_precios=[]
    view._fila_editor_precios=None
    view._toggle_opciones_rangos=mock.Mock()
    view.columns=COLS
    view.tree=Tree()
    view._pb_listado=Widget()
    view._update_validator_counts=mock.Mock()
    for name in ('btn_to_paste','lbl_listado','lbl_archivo_articulos','lbl_fecha_articulos','lbl_info','btn_exportar_precios','lbl_rangos_fuente','lbl_pegado_precios','btn_revisar_precios'):
        setattr(view,name,Widget())
    view.winfo_exists=lambda:True
    view.after=lambda delay,callback:callback()
    view._show=mock.Mock()
    view.stepC=object()
    return view

class PriceChangesTests(unittest.TestCase):
    def test_entrar_usa_archivo_guardado_sin_descargas_ni_tareas_programadas(self):
        root=types.SimpleNamespace(title=mock.Mock(),_actualizar_solo_articulos=mock.Mock())
        original_frame=app.ttk.Frame
        with mock.patch.object(original_frame,'__init__',autospec=True,side_effect=lambda widget,parent:setattr(widget,'master',parent)), \
             mock.patch.object(app.TivendoWindow,'pack'), mock.patch.object(app.ttk,'Frame'), \
             mock.patch.object(app.ttk,'Label'),mock.patch.object(app.ttk,'Button'), \
             mock.patch.object(app.tk,'BooleanVar'), \
             mock.patch.object(app.TivendoWindow,'_build_stepA_select_listado',autospec=True,side_effect=lambda s:setattr(s,'stepA',object())), \
             mock.patch.object(app.TivendoWindow,'_build_stepB_paste'), \
             mock.patch.object(app.TivendoWindow,'_build_stepC_preview'), \
             mock.patch.object(app.TivendoWindow,'_show'), \
             mock.patch.object(app.TivendoWindow,'_start_async_listado_load') as local_load, \
             mock.patch.object(app.TivendoWindow,'after_idle') as schedule:
            app.TivendoWindow(root,listado_path=Path('guardado.xlsx'))
            local_load.assert_called_once_with(Path('guardado.xlsx'))
            root._actualizar_solo_articulos.assert_not_called()
            schedule.assert_not_called()

    def test_solo_el_boton_manual_solicita_articulos(self):
        view=fixture()
        view.master=types.SimpleNamespace(_actualizar_solo_articulos=mock.Mock())
        view._start_async_listado_load=mock.Mock()
        view._actualizar_listado_precios()
        view.master._actualizar_solo_articulos.assert_called_once()
        callback=view.master._actualizar_solo_articulos.call_args.args[0]
        callback(Path('nuevo.xlsx'),object())
        view._start_async_listado_load.assert_called_once_with(Path('nuevo.xlsx'))

    def test_continuar_no_depende_de_una_lista_de_precios(self):
        view=fixture()
        view._actualizar_estado_continuar()
        self.assertEqual(view.btn_to_paste.options['state'],'normal')
        view._listado_cargando=True
        view._actualizar_estado_continuar()
        self.assertEqual(view.btn_to_paste.options['state'],'disabled')

    def test_tras_error_de_carga_se_puede_seguir_con_el_listado_anterior(self):
        view=fixture();old=view.df_map
        view._parse_listado_for_map=mock.Mock(side_effect=ValueError('archivo inválido'))
        with mock.patch.object(app.threading,'Thread',side_effect=lambda target,daemon:types.SimpleNamespace(start=target)),mock.patch.object(app.messagebox,'showerror') as error:
            view._start_async_listado_load(Path('fallido.xlsx'))
        self.assertIs(view.df_map,old)
        self.assertFalse(view._listado_cargando)
        self.assertEqual(view.btn_to_paste.options['state'],'normal')
        error.assert_called_once()

    def test_busca_el_articulo_y_exporta_solo_los_precios_nuevos(self):
        view=fixture()
        view._filas_pegado_precios=[['00123','','','1990','','',''], ['99999','','','2990','','','']]
        view._build_preview_from_paste()
        self.assertEqual(len(view.tree.rows),2)
        self.assertEqual(view.tree.rows['0']['Código'],'A022766')
        self.assertEqual(view.tree.rows['0']['Precio1'],'1990')
        self.assertEqual(view.tree.rows['0']['RangoExistente'],'Sí · (2 - 100)')
        self.assertEqual(view.tree.rows['1']['RangoExistente'],'Sin información')
        view.export_only_valid=types.SimpleNamespace(get=lambda:True)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'exportacion.xlsx'
            with mock.patch.object(app.filedialog,'asksaveasfilename',return_value=str(path)),mock.patch.object(app.messagebox,'showinfo'):
                view._export()
            output=app.pd.read_excel(path,dtype=str).fillna('')
        self.assertEqual(output.columns.tolist(),['Código','RangoInicial1','RangoFinal1','Precio1','RangoInicial2','RangoFinal2','Precio2'])
        self.assertEqual(output['Código'].tolist(),['A022766'])
        self.assertEqual(output['Precio1'].tolist(),['1990'])

    def test_los_rangos_compartidos_se_conservan_sin_copiar_precios_y_la_cache_se_renueva(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'rangos.xls';path.write_text(REPORT,encoding='utf-8')
            cache=Path(directory)/'cache.pkl';metadata=Path(directory)/'cache.json'
            app.pd.to_pickle((app.pd.DataFrame(),{'A022766':{'precio1':'1290','rango1':'viejo'}}),cache)
            metadata.write_text(json.dumps({'src_path':str(path),'src_mtime':path.stat().st_mtime,'schema_version':2}))
            _,index=app._load_cached_side_data(path,cache,metadata,app.load_price_ranges_data)
            self.assertEqual(index['A022766'],{'codigo':'A022766','rango1':'(1 - 9,999)','rango2':'(10 - 999)'})
            self.assertEqual(json.loads(metadata.read_text())['schema_version'],3)

    def test_distingue_rango_ausente_y_datos_desconocidos(self):
        self.assertEqual(app.resumen_rango_venta({}), 'Sin información')
        self.assertEqual(app.resumen_rango_venta({'rango2':'(0)'}), 'Sin rango adicional')
        self.assertEqual(app.resumen_rango_venta({'rango2':'(3 - 999)'}), 'Sí · (3 - 999)')

    def test_sin_archivo_o_archivo_invalido_no_hay_descargas_y_se_indica(self):
        for path in (None, Path('no_existe_rangos_145.xls')):
            index, label=app.rangos_guardados_para_revision(path)
            self.assertEqual(index,{})
            self.assertIn('sin archivo',label)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'roto.xls';path.write_text('archivo inválido')
            index,label=app.rangos_guardados_para_revision(path)
            self.assertEqual(index,{})
            self.assertIn('No se pudo leer',label)

    def test_las_funciones_retiradas_ya_no_existen(self):
        for name in ('auto_download_solo_precios','precio_actual_catalogo','save_auto_prices_load','price_download_label','ConvertView'):
            self.assertFalse(hasattr(app,name),name)
        self.assertFalse(hasattr(app.RootApp,'_actualizar_solo_precios'))
        self.assertFalse(hasattr(app.TivendoWindow,'_actualizar_precios_al_entrar'))

if __name__=='__main__':unittest.main()
