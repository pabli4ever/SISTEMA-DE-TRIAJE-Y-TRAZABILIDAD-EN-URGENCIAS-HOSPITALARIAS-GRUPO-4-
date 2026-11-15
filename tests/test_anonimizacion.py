"""Comprobaciones sin escribir en MongoDB ni consumir eventos de la API."""

import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import anonimizacion as anon
import etl_historico as etl
import triage_redis as triage
import urgencias_worker as worker


class TestAnonimizacion(unittest.TestCase):
    def setUp(self):
        # Clave fija exclusivamente de prueba; nunca sustituye la del archivo .env.
        cambio = patch.object(anon.settings, "ANON_HMAC_KEY", "11" * 32)
        cambio.start()
        self.addCleanup(cambio.stop)

    def comprobar_documento(self, valor):
        if isinstance(valor, dict):
            self.assertNotIn("nombre", valor)
            for campo, contenido in valor.items():
                if campo in ("sip", "sip_paciente") and contenido is not None:
                    self.assertRegex(contenido, r"^[0-9a-f]{32}$")
                if campo == "edad" and contenido is not None:
                    self.assertRegex(contenido, r"^\[\d+-\d+\]$")
                    inicio, fin = map(int, contenido[1:-1].split("-"))
                    self.assertEqual(inicio % 10, 0)
                    self.assertEqual(fin, inicio + 9)
                self.comprobar_documento(contenido)
        elif isinstance(valor, list):
            for contenido in valor:
                self.comprobar_documento(contenido)

    def test_hmac_conocido_normalizacion_y_cambio_de_clave(self):
        esperado = "49deda73747099007a5d25bb4d08f330"
        self.assertEqual(anon.anonimizar_sip("SIP-123456"), esperado)
        self.assertEqual(anon.anonimizar_sip(" sip-123456 "), esperado)
        with patch.object(anon.settings, "ANON_HMAC_KEY", "22" * 32):
            self.assertNotEqual(anon.anonimizar_sip("SIP-123456"), esperado)
        for ausente in (None, "", "N/D", "null"):
            self.assertIsNone(anon.anonimizar_sip(ausente))

    def test_edades_limites_y_valores_invalidos(self):
        casos = [(0, "[0-9]"), (9, "[0-9]"), (10, "[10-19]"),
                 ("64", "[60-69]"), (65, "[60-69]"), (100, "[100-109]")]
        for edad, esperado in casos:
            with self.subTest(edad=edad):
                self.assertEqual(anon.agrupar_edad(edad), esperado)
        for edad in (None, "", "N/D", -1, 121, True, 12.5, float("nan"), float("inf")):
            self.assertIsNone(anon.agrupar_edad(edad))

    def test_anidados_sin_modificar_el_original(self):
        original = {
            "id_episodio": "EP-PRUEBA", "sip_paciente": "SIP-123456", "nombre": "Prueba",
            "parte_clinico": {"edad": "64", "constantes": {"frecuencia_cardiaca": 80},
                              "lista": [{"nombre": "Prueba", "sip": "SIP-123456", "edad": 9}]},
        }
        copia = copy.deepcopy(original)
        resultado = anon.anonimizar_documento(original)
        self.comprobar_documento(resultado)
        self.assertEqual(original, copia)
        self.assertEqual(resultado["parte_clinico"]["edad"], "[60-69]")
        self.assertEqual(resultado["sip_paciente"], resultado["parte_clinico"]["lista"][0]["sip"])
        self.assertEqual(resultado["parte_clinico"]["constantes"], original["parte_clinico"]["constantes"])

    def test_clave_invalida_bloquea_mongo_y_la_api(self):
        for clave in ("", "corta", "z" * 64):
            with self.subTest(clave=clave), patch.object(anon.settings, "ANON_HMAC_KEY", clave), \
                    patch.object(etl, "MongoClient") as mongo, patch.object(worker, "consultar_api") as api:
                with self.assertRaises(ValueError):
                    etl.guardar_mongodb([{"id_episodio": "EP-PRUEBA", "sip_paciente": "SIP-123456"}])
                with self.assertRaises(ValueError):
                    worker.main()
                mongo.assert_not_called()
                api.assert_not_called()

    def test_json_y_mongo_reciben_el_mismo_hash_una_sola_vez(self):
        original = {"id_episodio": "EP-PRUEBA", "sip_paciente": "SIP-123456", "edad": 64, "nombre": "Prueba"}
        with tempfile.TemporaryDirectory() as directorio, patch.object(etl, "MongoClient") as mongo, \
                contextlib.redirect_stdout(io.StringIO()):
            ruta = etl.exportar_json([original], Path(directorio) / "salida.json")
            exportado = json.loads(ruta.read_text(encoding="utf-8"))
            etl.guardar_mongodb([original])
            cliente = mongo.return_value.__enter__.return_value
            coleccion = cliente[etl.settings.MONGO_DATABASE][etl.settings.MONGO_COLLECTION]
            operacion = coleccion.bulk_write.call_args.args[0][0]
            self.assertEqual(exportado, [operacion._doc])
            self.assertEqual(operacion._doc["sip_paciente"], "49deda73747099007a5d25bb4d08f330")
            self.assertEqual(operacion._filter, {"id_episodio": "EP-PRUEBA"})
            self.assertTrue(operacion._upsert)
            self.assertEqual(original["sip_paciente"], "SIP-123456")
            self.comprobar_documento(exportado)

    def test_alta_incorpora_el_sip_final_y_elimina_nulos(self):
        ingreso = {"id_episodio": "EP-PRUEBA", "datos_admision": {
            "sip_paciente": "SIP-111111", "nombre": "Prueba", "edad": 64},
            "datos_triaje": {"nivel_manchester": 3, "modulo_pediatria": None}}
        alta = {"id_episodio": "EP-PRUEBA", "sip_paciente": "SIP-123456", "destino_alta": "domicilio"}
        with patch.object(triage, "redis_client") as redis, patch.object(triage, "MongoClient") as mongo, \
                contextlib.redirect_stdout(io.StringIO()):
            redis.hgetall.return_value = {"documento": json.dumps(ingreso)}
            triage.procesar_altas({"pacientes_alta": [alta]})
            coleccion = mongo.return_value[triage.settings.MONGO_DATABASE][triage.settings.MONGO_COLLECTION]
            guardado = coleccion.replace_one.call_args.args[1]
            self.comprobar_documento(guardado)
            self.assertEqual(guardado["sip_paciente"], "49deda73747099007a5d25bb4d08f330")
            self.assertEqual(guardado["edad"], "[60-69]")
            self.assertNotIn("modulo_pediatria", guardado)
            redis.delete.assert_any_call("episodio:EP-PRUEBA")

    def test_alta_elimina_tambien_los_nulos_generados_al_transformar(self):
        original = {"id_episodio": "EP-PRUEBA", "datos_admision": {
            "sip_paciente": "N/D", "nombre": "Prueba", "edad": "ERROR"}}
        with patch.object(triage, "MongoClient") as mongo, contextlib.redirect_stdout(io.StringIO()):
            triage.cargar_datos_mongo(original)
            coleccion = mongo.return_value[triage.settings.MONGO_DATABASE][triage.settings.MONGO_COLLECTION]
            self.assertEqual(coleccion.replace_one.call_args.args[1], {"id_episodio": "EP-PRUEBA"})

    def test_historico_completo_conserva_episodios_y_correspondencias(self):
        datos = etl.procesar_historico()
        self.assertTrue(datos)
        self.assertEqual(len({d["id_episodio"] for d in datos}), len(datos))
        with tempfile.TemporaryDirectory() as directorio, contextlib.redirect_stdout(io.StringIO()):
            ruta = etl.exportar_json(datos, Path(directorio) / "historico.json")
            protegido = json.loads(ruta.read_text(encoding="utf-8"))
        self.assertIsInstance(protegido, list)
        self.assertEqual(len(protegido), len(datos))
        self.comprobar_documento(protegido)
        correspondencias = {}
        for original, salida in zip(datos, protegido):
            self.assertEqual(original["id_episodio"], salida["id_episodio"])
            sip = original["sip_paciente"].strip().upper()
            self.assertEqual(correspondencias.setdefault(sip, salida["sip_paciente"]), salida["sip_paciente"])
        self.assertEqual(len(set(correspondencias.values())), len(correspondencias))


if __name__ == "__main__":
    unittest.main()
