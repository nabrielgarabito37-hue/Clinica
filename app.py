# -*- coding: utf-8 -*-
"""
Servidor del Sistema de Clinica Rural.
Corre 100% localmente, sin necesidad de internet.
"""
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime

from database import get_connection, init_db, now_iso

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")


def row_to_dict(row):
    return dict(row) if row else None


def rows_to_list(rows):
    return [dict(r) for r in rows]


# ============================================================
# SERVIR EL FRONTEND
# ============================================================
@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


# ============================================================
# AUTENTICACION
# ============================================================
@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    usuario = data.get("usuario", "").strip()
    password = data.get("password", "")

    conn = get_connection()
    user = conn.execute(
        "SELECT * FROM usuarios WHERE usuario = ? AND activo = 1", (usuario,)
    ).fetchone()
    conn.close()

    if user and check_password_hash(user["password_hash"], password):
        user_dict = row_to_dict(user)
        user_dict.pop("password_hash")
        return jsonify({"ok": True, "usuario": user_dict})
    return jsonify({"ok": False, "error": "Usuario o contraseña incorrectos"}), 401


# ============================================================
# USUARIOS (doctores, enfermeras, recepcion)
# ============================================================
@app.route("/api/usuarios", methods=["GET"])
def listar_usuarios():
    conn = get_connection()
    usuarios = conn.execute(
        "SELECT id, nombre_completo, usuario, rol, especialidad, activo FROM usuarios ORDER BY nombre_completo"
    ).fetchall()
    conn.close()
    return jsonify(rows_to_list(usuarios))


@app.route("/api/usuarios", methods=["POST"])
def crear_usuario():
    data = request.get_json()
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO usuarios (nombre_completo, usuario, password_hash, rol, especialidad, creado_en)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            data["nombre_completo"], data["usuario"],
            generate_password_hash(data["password"]), data["rol"],
            data.get("especialidad"), now_iso()
        ))
        conn.commit()
        new_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
        return jsonify({"ok": True, "id": new_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        conn.close()


@app.route("/api/usuarios/<int:user_id>", methods=["PUT"])
def actualizar_usuario(user_id):
    data = request.get_json()
    conn = get_connection()
    try:
        if data.get("password"):
            conn.execute("""
                UPDATE usuarios SET nombre_completo=?, rol=?, especialidad=?, activo=?, password_hash=?
                WHERE id=?
            """, (data["nombre_completo"], data["rol"], data.get("especialidad"),
                  data.get("activo", 1), generate_password_hash(data["password"]), user_id))
        else:
            conn.execute("""
                UPDATE usuarios SET nombre_completo=?, rol=?, especialidad=?, activo=?
                WHERE id=?
            """, (data["nombre_completo"], data["rol"], data.get("especialidad"),
                  data.get("activo", 1), user_id))
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        conn.close()


# ============================================================
# PACIENTES
# ============================================================
def generar_expediente(conn):
    year = datetime.now().year
    count = conn.execute(
        "SELECT COUNT(*) as c FROM pacientes WHERE expediente LIKE ?", (f"EXP-{year}-%",)
    ).fetchone()["c"]
    return f"EXP-{year}-{count + 1:04d}"


@app.route("/api/pacientes", methods=["GET"])
def listar_pacientes():
    busqueda = request.args.get("q", "").strip()
    conn = get_connection()
    if busqueda:
        like = f"%{busqueda}%"
        pacientes = conn.execute("""
            SELECT * FROM pacientes
            WHERE activo = 1 AND (nombre_completo LIKE ? OR expediente LIKE ? OR cedula_identidad LIKE ?)
            ORDER BY nombre_completo
        """, (like, like, like)).fetchall()
    else:
        pacientes = conn.execute(
            "SELECT * FROM pacientes WHERE activo = 1 ORDER BY nombre_completo"
        ).fetchall()
    conn.close()
    return jsonify(rows_to_list(pacientes))


@app.route("/api/pacientes/<int:paciente_id>", methods=["GET"])
def obtener_paciente(paciente_id):
    conn = get_connection()
    paciente = conn.execute("SELECT * FROM pacientes WHERE id = ?", (paciente_id,)).fetchone()
    conn.close()
    if not paciente:
        return jsonify({"error": "Paciente no encontrado"}), 404
    return jsonify(row_to_dict(paciente))


@app.route("/api/pacientes", methods=["POST"])
def crear_paciente():
    data = request.get_json()
    conn = get_connection()
    try:
        expediente = generar_expediente(conn)
        ts = now_iso()
        conn.execute("""
            INSERT INTO pacientes (
                expediente, nombre_completo, fecha_nacimiento, sexo, cedula_identidad,
                telefono, direccion, contacto_emergencia_nombre, contacto_emergencia_telefono,
                tipo_sangre, alergias, condiciones_cronicas, creado_en, actualizado_en
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            expediente, data["nombre_completo"], data.get("fecha_nacimiento"),
            data.get("sexo"), data.get("cedula_identidad"), data.get("telefono"),
            data.get("direccion"), data.get("contacto_emergencia_nombre"),
            data.get("contacto_emergencia_telefono"), data.get("tipo_sangre"),
            data.get("alergias"), data.get("condiciones_cronicas"), ts, ts
        ))
        conn.commit()
        new_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
        return jsonify({"ok": True, "id": new_id, "expediente": expediente})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        conn.close()


@app.route("/api/pacientes/<int:paciente_id>", methods=["PUT"])
def actualizar_paciente(paciente_id):
    data = request.get_json()
    conn = get_connection()
    try:
        conn.execute("""
            UPDATE pacientes SET
                nombre_completo=?, fecha_nacimiento=?, sexo=?, cedula_identidad=?,
                telefono=?, direccion=?, contacto_emergencia_nombre=?, contacto_emergencia_telefono=?,
                tipo_sangre=?, alergias=?, condiciones_cronicas=?, actualizado_en=?
            WHERE id=?
        """, (
            data["nombre_completo"], data.get("fecha_nacimiento"), data.get("sexo"),
            data.get("cedula_identidad"), data.get("telefono"), data.get("direccion"),
            data.get("contacto_emergencia_nombre"), data.get("contacto_emergencia_telefono"),
            data.get("tipo_sangre"), data.get("alergias"), data.get("condiciones_cronicas"),
            now_iso(), paciente_id
        ))
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        conn.close()


@app.route("/api/pacientes/<int:paciente_id>", methods=["DELETE"])
def eliminar_paciente(paciente_id):
    conn = get_connection()
    conn.execute("UPDATE pacientes SET activo = 0 WHERE id = ?", (paciente_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ============================================================
# CITAS / TURNOS
# ============================================================
@app.route("/api/citas", methods=["GET"])
def listar_citas():
    fecha = request.args.get("fecha", "").strip()
    conn = get_connection()
    query = """
        SELECT c.*, p.nombre_completo as paciente_nombre, p.expediente,
               u.nombre_completo as doctor_nombre
        FROM citas c
        JOIN pacientes p ON c.paciente_id = p.id
        LEFT JOIN usuarios u ON c.doctor_id = u.id
    """
    params = ()
    if fecha:
        query += " WHERE c.fecha = ?"
        params = (fecha,)
    query += " ORDER BY c.fecha, c.hora"
    citas = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify(rows_to_list(citas))


@app.route("/api/citas", methods=["POST"])
def crear_cita():
    data = request.get_json()
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO citas (paciente_id, doctor_id, fecha, hora, motivo, estado, notas, creado_en)
            VALUES (?, ?, ?, ?, ?, 'pendiente', ?, ?)
        """, (
            data["paciente_id"], data.get("doctor_id"), data["fecha"], data["hora"],
            data.get("motivo"), data.get("notas"), now_iso()
        ))
        conn.commit()
        new_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
        return jsonify({"ok": True, "id": new_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        conn.close()


@app.route("/api/citas/<int:cita_id>", methods=["PUT"])
def actualizar_cita(cita_id):
    data = request.get_json()
    conn = get_connection()
    try:
        conn.execute("""
            UPDATE citas SET paciente_id=?, doctor_id=?, fecha=?, hora=?, motivo=?, estado=?, notas=?
            WHERE id=?
        """, (
            data["paciente_id"], data.get("doctor_id"), data["fecha"], data["hora"],
            data.get("motivo"), data.get("estado", "pendiente"), data.get("notas"), cita_id
        ))
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        conn.close()


@app.route("/api/citas/<int:cita_id>", methods=["DELETE"])
def eliminar_cita(cita_id):
    conn = get_connection()
    conn.execute("DELETE FROM citas WHERE id = ?", (cita_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ============================================================
# CONSULTAS (Historial Medico)
# ============================================================
@app.route("/api/pacientes/<int:paciente_id>/consultas", methods=["GET"])
def historial_paciente(paciente_id):
    conn = get_connection()
    consultas = conn.execute("""
        SELECT c.*, u.nombre_completo as doctor_nombre
        FROM consultas c
        JOIN usuarios u ON c.doctor_id = u.id
        WHERE c.paciente_id = ?
        ORDER BY c.fecha DESC
    """, (paciente_id,)).fetchall()
    resultado = []
    for consulta in consultas:
        c_dict = dict(consulta)
        recetas = conn.execute(
            "SELECT * FROM recetas WHERE consulta_id = ?", (consulta["id"],)
        ).fetchall()
        c_dict["recetas"] = rows_to_list(recetas)
        resultado.append(c_dict)
    conn.close()
    return jsonify(resultado)


@app.route("/api/consultas", methods=["POST"])
def crear_consulta():
    data = request.get_json()
    conn = get_connection()
    try:
        cur = conn.execute("""
            INSERT INTO consultas (
                paciente_id, doctor_id, cita_id, fecha, motivo_consulta, sintomas,
                presion_arterial, temperatura, frecuencia_cardiaca, peso_kg, altura_cm,
                diagnostico, tratamiento, observaciones, requiere_seguimiento, creado_en
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["paciente_id"], data["doctor_id"], data.get("cita_id"),
            data.get("fecha", now_iso()), data.get("motivo_consulta"), data.get("sintomas"),
            data.get("presion_arterial"), data.get("temperatura"), data.get("frecuencia_cardiaca"),
            data.get("peso_kg"), data.get("altura_cm"), data.get("diagnostico"),
            data.get("tratamiento"), data.get("observaciones"),
            1 if data.get("requiere_seguimiento") else 0, now_iso()
        ))
        consulta_id = cur.lastrowid

        # Si vino de una cita, marcarla como atendida
        if data.get("cita_id"):
            conn.execute("UPDATE citas SET estado = 'atendida' WHERE id = ?", (data["cita_id"],))

        # Procesar recetas y descontar inventario
        for receta in data.get("recetas", []):
            conn.execute("""
                INSERT INTO recetas (consulta_id, medicamento_id, nombre_medicamento, dosis, frecuencia, duracion, cantidad_entregada)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                consulta_id, receta.get("medicamento_id"), receta["nombre_medicamento"],
                receta.get("dosis"), receta.get("frecuencia"), receta.get("duracion"),
                receta.get("cantidad_entregada", 0)
            ))
            # Descontar del inventario si corresponde
            if receta.get("medicamento_id") and receta.get("cantidad_entregada"):
                conn.execute("""
                    UPDATE medicamentos SET cantidad_disponible = cantidad_disponible - ?, actualizado_en = ?
                    WHERE id = ?
                """, (receta["cantidad_entregada"], now_iso(), receta["medicamento_id"]))
                conn.execute("""
                    INSERT INTO movimientos_inventario (medicamento_id, tipo, cantidad, motivo, usuario_id, fecha)
                    VALUES (?, 'salida', ?, ?, ?, ?)
                """, (
                    receta["medicamento_id"], receta["cantidad_entregada"],
                    f"Receta - Consulta #{consulta_id}", data["doctor_id"], now_iso()
                ))

        conn.commit()
        return jsonify({"ok": True, "id": consulta_id})
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        conn.close()


# ============================================================
# INVENTARIO DE MEDICINAS
# ============================================================
@app.route("/api/medicamentos", methods=["GET"])
def listar_medicamentos():
    busqueda = request.args.get("q", "").strip()
    solo_bajos = request.args.get("bajos", "") == "1"
    conn = get_connection()
    query = "SELECT * FROM medicamentos"
    conditions = []
    params = []
    if busqueda:
        conditions.append("nombre LIKE ?")
        params.append(f"%{busqueda}%")
    if solo_bajos:
        conditions.append("cantidad_disponible <= cantidad_minima")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY nombre"
    medicamentos = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify(rows_to_list(medicamentos))


@app.route("/api/medicamentos", methods=["POST"])
def crear_medicamento():
    data = request.get_json()
    conn = get_connection()
    try:
        cur = conn.execute("""
            INSERT INTO medicamentos (nombre, presentacion, cantidad_disponible, cantidad_minima, fecha_vencimiento, lote, proveedor, actualizado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["nombre"], data.get("presentacion"), data.get("cantidad_disponible", 0),
            data.get("cantidad_minima", 10), data.get("fecha_vencimiento"),
            data.get("lote"), data.get("proveedor"), now_iso()
        ))
        med_id = cur.lastrowid
        if data.get("cantidad_disponible", 0) > 0:
            conn.execute("""
                INSERT INTO movimientos_inventario (medicamento_id, tipo, cantidad, motivo, usuario_id, fecha)
                VALUES (?, 'entrada', ?, 'Registro inicial', ?, ?)
            """, (med_id, data.get("cantidad_disponible", 0), data.get("usuario_id"), now_iso()))
        conn.commit()
        return jsonify({"ok": True, "id": med_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        conn.close()


@app.route("/api/medicamentos/<int:med_id>", methods=["PUT"])
def actualizar_medicamento(med_id):
    data = request.get_json()
    conn = get_connection()
    try:
        conn.execute("""
            UPDATE medicamentos SET nombre=?, presentacion=?, cantidad_minima=?, fecha_vencimiento=?, lote=?, proveedor=?, actualizado_en=?
            WHERE id=?
        """, (
            data["nombre"], data.get("presentacion"), data.get("cantidad_minima", 10),
            data.get("fecha_vencimiento"), data.get("lote"), data.get("proveedor"), now_iso(), med_id
        ))
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        conn.close()


@app.route("/api/medicamentos/<int:med_id>/movimiento", methods=["POST"])
def registrar_movimiento(med_id):
    """Para entradas manuales de stock (ej. llego un pedido) o ajustes."""
    data = request.get_json()
    tipo = data["tipo"]  # 'entrada', 'salida', 'ajuste'
    cantidad = int(data["cantidad"])
    conn = get_connection()
    try:
        if tipo == "entrada":
            conn.execute("UPDATE medicamentos SET cantidad_disponible = cantidad_disponible + ?, actualizado_en = ? WHERE id = ?",
                         (cantidad, now_iso(), med_id))
        elif tipo == "salida":
            conn.execute("UPDATE medicamentos SET cantidad_disponible = cantidad_disponible - ?, actualizado_en = ? WHERE id = ?",
                         (cantidad, now_iso(), med_id))
        elif tipo == "ajuste":
            conn.execute("UPDATE medicamentos SET cantidad_disponible = ?, actualizado_en = ? WHERE id = ?",
                         (cantidad, now_iso(), med_id))

        conn.execute("""
            INSERT INTO movimientos_inventario (medicamento_id, tipo, cantidad, motivo, usuario_id, fecha)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (med_id, tipo, cantidad, data.get("motivo", ""), data.get("usuario_id"), now_iso()))
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        conn.close()


@app.route("/api/medicamentos/<int:med_id>/movimientos", methods=["GET"])
def historial_movimientos(med_id):
    conn = get_connection()
    movimientos = conn.execute("""
        SELECT m.*, u.nombre_completo as usuario_nombre
        FROM movimientos_inventario m
        LEFT JOIN usuarios u ON m.usuario_id = u.id
        WHERE m.medicamento_id = ?
        ORDER BY m.fecha DESC
    """, (med_id,)).fetchall()
    conn.close()
    return jsonify(rows_to_list(movimientos))


# ============================================================
# DASHBOARD / RESUMEN
# ============================================================
@app.route("/api/dashboard", methods=["GET"])
def dashboard():
    conn = get_connection()
    hoy = datetime.now().strftime("%Y-%m-%d")

    total_pacientes = conn.execute("SELECT COUNT(*) as c FROM pacientes WHERE activo = 1").fetchone()["c"]
    citas_hoy = conn.execute("SELECT COUNT(*) as c FROM citas WHERE fecha = ?", (hoy,)).fetchone()["c"]
    citas_pendientes_hoy = conn.execute(
        "SELECT COUNT(*) as c FROM citas WHERE fecha = ? AND estado = 'pendiente'", (hoy,)
    ).fetchone()["c"]
    medicamentos_bajos = conn.execute(
        "SELECT COUNT(*) as c FROM medicamentos WHERE cantidad_disponible <= cantidad_minima"
    ).fetchone()["c"]
    consultas_mes = conn.execute("""
        SELECT COUNT(*) as c FROM consultas WHERE fecha LIKE ?
    """, (datetime.now().strftime("%Y-%m") + "%",)).fetchone()["c"]

    conn.close()
    return jsonify({
        "total_pacientes": total_pacientes,
        "citas_hoy": citas_hoy,
        "citas_pendientes_hoy": citas_pendientes_hoy,
        "medicamentos_bajos": medicamentos_bajos,
        "consultas_mes": consultas_mes
    })


if __name__ == "__main__":
    init_db()
    print("=" * 50)
    print("  Sistema de Clinica Rural")
    print("  Servidor iniciado correctamente")
    print("  Abra su navegador en: http://localhost:5000")
    print("=" * 50)
    app.run(host="127.0.0.1", port=5000, debug=False)
