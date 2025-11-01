import os
import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func # Para usar funciones como SUM y AVG
from sqlalchemy import distinct # Para buscar materiales únicos
from weasyprint import HTML 

# --- Configuración Inicial ---
basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mi-clave-secreta-para-sesiones-12345'
app.config['SQLALCHEMY_DATABASE_URI'] = \
    'sqlite:///' + os.path.join(basedir, 'inventario_v5.db') 
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Listas Estáticas de Opciones ---
PROVEEDORES = ["GASA", "TERNIUM"] 
MAQUINAS = [
    "TR-01", "TR-02", "TR-03", "TR-04", "TR-05", "TR-06",
    "TR-07", "TR-08", "TR-09", "ESTRIBO"
]

# --- Modelos de la Base de Datos (V5) ---
class Conteo_Inventario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rol = db.Column(db.String(50)) 
    usuario = db.Column(db.String(100)) 
    grado_acero = db.Column(db.String(100)) 
    diametro = db.Column(db.Float) 
    proveedor = db.Column(db.String(50))
    cantidad_rollos = db.Column(db.Integer, default=0, nullable=True)
    peso1 = db.Column(db.Float, nullable=True)
    peso2 = db.Column(db.Float, nullable=True)
    peso3 = db.Column(db.Float, nullable=True)
    peso4 = db.Column(db.Float, nullable=True)
    peso5 = db.Column(db.Float, nullable=True)
    exacto1 = db.Column(db.Float, nullable=True)
    exacto2 = db.Column(db.Float, nullable=True)
    exacto3 = db.Column(db.Float, nullable=True)
    fecha_creado = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Registro_Maquina(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(100))
    fecha_creado = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    maquina = db.Column(db.String(50))
    grado_acero = db.Column(db.String(100))
    diametro = db.Column(db.Float)
    peso1 = db.Column(db.Float, nullable=True)
    peso2 = db.Column(db.Float, nullable=True)
    peso3 = db.Column(db.Float, nullable=True)
    peso4 = db.Column(db.Float, nullable=True)
    peso5 = db.Column(db.Float, nullable=True)

# --- Funciones Auxiliares ---
def a_float_o_cero(valor):
    try:
        val = float(valor)
        return val if val > 0 else 0.0
    except (ValueError, TypeError):
        return 0.0

def es_admin():
    return session.get('rol') == 'Admin'

# --- Función Helper del Reporte V5 ---
def obtener_datos_reporte():
    materiales_unicos = db.session.query(
        Conteo_Inventario.grado_acero,
        Conteo_Inventario.diametro,
        Conteo_Inventario.proveedor
    ).distinct().all()
    reporte_final = []
    for mat in materiales_unicos:
        total_rollos = db.session.query(
            func.sum(Conteo_Inventario.cantidad_rollos)
        ).filter_by(
            rol='Invitado', grado_acero=mat.grado_acero,
            diametro=mat.diametro, proveedor=mat.proveedor
        ).scalar() or 0
        registros_pesos_admin = Conteo_Inventario.query.filter_by(
            rol='Admin', grado_acero=mat.grado_acero,
            diametro=mat.diametro, proveedor=mat.proveedor
        ).all()
        pesos_para_promedio = []
        for reg in registros_pesos_admin:
            pesos_para_promedio.extend([
                reg.peso1, reg.peso2, reg.peso3, reg.peso4, reg.peso5
            ])
        valid_pesos = [p for p in pesos_para_promedio if p and p > 0]
        if valid_pesos:
            display_peso = sum(valid_pesos) / len(valid_pesos)
            display_tipo = "(Prom)"
        else:
            display_peso = 0
            display_tipo = "(Sin Pesos)"
        reporte_final.append({
            'grado': mat.grado_acero, 'diametro': mat.diametro,
            'proveedor': mat.proveedor, 'total_rollos': total_rollos,
            'registros_pesos': registros_pesos_admin, 
            'display_peso': display_peso, 'display_tipo': display_tipo
        })
    return reporte_final

# --- Pantalla 1: Inicio (Login) ---
@app.route('/')
def index():
    session.clear() 
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    if 'rol' in request.form and request.form['rol'] == 'Admin':
        session['rol'] = 'Admin'
        session['usuario'] = 'Admin'
    elif 'nombre_invitado' in request.form and request.form['nombre_invitado']:
        session['rol'] = 'Invitado'
        session['usuario'] = request.form['nombre_invitado'].strip()
    else:
        return redirect(url_for('index')) 
    return redirect(url_for('ingresar')) 

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- Pantalla 2: Ingreso de Inventario (V5) ---
@app.route('/ingresar')
def ingresar():
    if 'rol' not in session:
        return redirect(url_for('index')) 
    materiales_admin = db.session.query(
        Conteo_Inventario.grado_acero,
        Conteo_Inventario.diametro
    ).filter_by(rol='Admin').distinct().all()
    grados_invitado = sorted(list(set([m.grado_acero for m in materiales_admin])))
    diametros_invitado = sorted(list(set([m.diametro for m in materiales_admin])))
    return render_template('ingresar.html',
                           proveedores=PROVEEDORES,
                           grados_invitado=grados_invitado,
                           diametros_invitado=diametros_invitado
                           )

# --- (Función de Guardado V5.3) ---
@app.route('/guardar-inventario', methods=['POST'])
def guardar_inventario():
    if 'rol' not in session:
        return redirect(url_for('index'))

    if es_admin():
        # Lógica de guardado para ADMIN (Actualiza si existe)
        grado = request.form['grado_acero'].strip()
        diametro = a_float_o_cero(request.form['diametro'])
        proveedor = request.form['proveedor']
        
        registro_existente = Conteo_Inventario.query.filter_by(
            rol='Admin',
            grado_acero=grado,
            diametro=diametro,
            proveedor=proveedor
        ).first()

        if registro_existente:
            # Si SÍ existe, ACTUALÍZALO
            registro_existente.peso1=a_float_o_cero(request.form.get('peso1'))
            registro_existente.peso2=a_float_o_cero(request.form.get('peso2'))
            registro_existente.peso3=a_float_o_cero(request.form.get('peso3'))
            registro_existente.peso4=a_float_o_cero(request.form.get('peso4'))
            registro_existente.peso5=a_float_o_cero(request.form.get('peso5'))
            registro_existente.exacto1=a_float_o_cero(request.form.get('exacto1'))
            registro_existente.exacto2=a_float_o_cero(request.form.get('exacto2'))
            registro_existente.exacto3=a_float_o_cero(request.form.get('exacto3'))
            flash('Pesos ACTUALIZADOS exitosamente!', 'success')
        else:
            # Si NO existe, CRÉALO
            nuevo_conteo = Conteo_Inventario(
                rol='Admin',
                usuario='Admin',
                grado_acero=grado,
                diametro=diametro,
                proveedor=proveedor,
                cantidad_rollos=0, 
                peso1=a_float_o_cero(request.form.get('peso1')),
                peso2=a_float_o_cero(request.form.get('peso2')),
                peso3=a_float_o_cero(request.form.get('peso3')),
                peso4=a_float_o_cero(request.form.get('peso4')),
                peso5=a_float_o_cero(request.form.get('peso5')),
                exacto1=a_float_o_cero(request.form.get('exacto1')),
                exacto2=a_float_o_cero(request.form.get('exacto2')),
                exacto3=a_float_o_cero(request.form.get('exacto3')),
            )
            db.session.add(nuevo_conteo)
            flash('Pesos CREADOS exitosamente!', 'success')
    else:
        # Lógica de guardado para INVITADO (Crea nueva fila)
        nuevo_conteo = Conteo_Inventario(
            rol='Invitado',
            usuario=session['usuario'],
            grado_acero=request.form['grado_acero'],
            diametro=a_float_o_cero(request.form['diametro']),
            proveedor=request.form['proveedor'],
            cantidad_rollos=int(a_float_o_cero(request.form['cantidad_rollos']))
        )
        db.session.add(nuevo_conteo)
        flash('Conteo de rollos guardado!', 'success')
    
    db.session.commit()
    
    return redirect(url_for('ingresar')) 

# --- Pantalla 3: Reporte Final (Inventario) (V5) ---
@app.route('/reporte')
def reporte():
    if 'rol' not in session:
        return redirect(url_for('index'))
    reporte_final = obtener_datos_reporte() 
    return render_template('reporte.html', reporte=reporte_final)

# --- Ruta PDF de Inventario (V5) ---
@app.route('/reporte/pdf')
def reporte_pdf():
    if 'rol' not in session:
        return redirect(url_for('index'))
    reporte_final = obtener_datos_reporte() 
    html_renderizado = render_template('pdf_reporte.html', reporte=reporte_final)
    pdf = HTML(string=html_renderizado).write_pdf()
    return Response(pdf,
                    mimetype='application/pdf',
                    headers={'Content-Disposition':
                             'attachment;filename=reporte_inventario.pdf'})

# --- Pantalla 4: Panel de Borrado (Admin) (V5) ---
@app.route('/panel-borrado')
def panel_borrado():
    if not es_admin():
        return redirect(url_for('index'))
    conteos_invitados = Conteo_Inventario.query.filter_by(rol='Invitado')\
        .order_by(Conteo_Inventario.fecha_creado.desc()).all()
    conteos_admin = Conteo_Inventario.query.filter_by(rol='Admin')\
        .order_by(Conteo_Inventario.fecha_creado.desc()).all()
    registros_maquinas = Registro_Maquina.query.order_by(Registro_Maquina.fecha_creado.desc()).all()
    return render_template('panel_borrado.html', 
                           conteos_invitados=conteos_invitados,
                           conteos_admin=conteos_admin,
                           registros_maquinas=registros_maquinas) 

@app.route('/borrar-conteo/<int:id>', methods=['POST'])
def borrar_conteo(id):
    if not es_admin():
        return redirect(url_for('index'))
    conteo_a_borrar = Conteo_Inventario.query.get_or_404(id)
    db.session.delete(conteo_a_borrar)
    db.session.commit()
    flash('Registro de inventario borrado.', 'success')
    return redirect(url_for('panel_borrado'))

@app.route('/borrar-maquina/<int:id>', methods=['POST'])
def borrar_maquina(id):
    if not es_admin(): 
        return redirect(url_for('index'))
    maquina_a_borrar = Registro_Maquina.query.get_or_404(id)
    db.session.delete(maquina_a_borrar)
    db.session.commit()
    flash('Registro de máquina borrado.', 'success')
    return redirect(url_for('panel_borrado'))

# --- Pantalla 5: Ingreso de Máquinas (¡Revisado V5.3!) ---
@app.route('/maquinas')
def maquinas():
    if session.get('rol') != 'Invitado':
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('ingresar'))
        
    # (LÓGICA DINÁMICA) Usa las listas de lo que el Admin ha ingresado
    materiales_admin = db.session.query(
        Conteo_Inventario.grado_acero,
        Conteo_Inventario.diametro
    ).filter_by(rol='Admin').distinct().all()
    
    grados_invitado = sorted(list(set([m.grado_acero for m in materiales_admin])))
    diametros_invitado = sorted(list(set([m.diametro for m in materiales_admin])))

    return render_template('maquinas.html',
                           maquinas=MAQUINAS,
                           grados_invitado=grados_invitado, # <-- Lista dinámica
                           diametros_invitado=diametros_invitado) # <-- Lista dinámica

@app.route('/guardar-maquina', methods=['POST'])
def guardar_maquina():
    if session.get('rol') != 'Invitado':
        return redirect(url_for('index'))
    nuevo_registro = Registro_Maquina(
        usuario=session['usuario'], 
        maquina=request.form['maquina'],
        grado_acero=request.form['grado_acero'],
        diametro=a_float_o_cero(request.form['diametro']),
        peso1 = a_float_o_cero(request.form.get('peso1')),
        peso2 = a_float_o_cero(request.form.get('peso2')),
        peso3 = a_float_o_cero(request.form.get('peso3')),
        peso4 = a_float_o_cero(request.form.get('peso4')),
        peso5 = a_float_o_cero(request.form.get('peso5'))
    )
    db.session.add(nuevo_registro)
    db.session.commit()
    flash('¡Registro de máquina guardado!', 'success')
    return redirect(url_for('reporte_maquinas')) 

# --- Pantalla 6: Reporte de Máquinas (SOLO INVITADO) ---
@app.route('/reporte-maquinas')
def reporte_maquinas():
    if session.get('rol') != 'Invitado':
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('ingresar'))
    registros = Registro_Maquina.query.order_by(Registro_Maquina.fecha_creado.desc()).all()
    return render_template('reporte_maquinas.html', registros=registros)

@app.route('/reporte-maquinas/pdf')
def reporte_maquinas_pdf():
    if session.get('rol') != 'Invitado':
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('ingresar'))
    registros = Registro_Maquina.query.order_by(Registro_Maquina.fecha_creado.desc()).all()
    html_renderizado = render_template('pdf_reporte_maquinas.html', registros=registros)
    pdf = HTML(string=html_renderizado).write_pdf()
    return Response(pdf,
                    mimetype='application/pdf',
                    headers={'Content-Disposition':
                             'attachment;filename=reporte_maquinas.pdf'})

# --- Ejecutar la App ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all() 
    app.run(debug=True, host='0.0.0.0')