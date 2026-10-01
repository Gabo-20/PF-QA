-- Esquema de base de datos para MySQL (Hostinger).
-- Alternativa manual a `Base.metadata.create_all()` de SQLAlchemy: úsalo si prefieres
-- crear las tablas directamente desde phpMyAdmin o la consola MySQL de hPanel.
-- Ejecuta este script sobre la base de datos MySQL vacía que crees en Hostinger.

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL,
    email VARCHAR(180) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    rol ENUM('admin','cajero') NOT NULL DEFAULT 'cajero',
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sku VARCHAR(50) NOT NULL UNIQUE,
    nombre VARCHAR(150) NOT NULL,
    categoria VARCHAR(80) NOT NULL,
    precio DOUBLE NOT NULL,
    costo DOUBLE NOT NULL DEFAULT 0,
    stock_actual INT NOT NULL DEFAULT 0,
    stock_minimo INT NOT NULL DEFAULT 5,
    lead_time_dias_china INT NOT NULL DEFAULT 60,
    activo BOOLEAN NOT NULL DEFAULT TRUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS sales (
    id INT AUTO_INCREMENT PRIMARY KEY,
    fecha_hora DATETIME NOT NULL,
    cajero_id INT NOT NULL,
    canal VARCHAR(40) DEFAULT 'Tienda',
    total DOUBLE NOT NULL DEFAULT 0,
    metodo_pago VARCHAR(40) DEFAULT 'Efectivo',
    FOREIGN KEY (cajero_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS sale_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sale_id INT NOT NULL,
    product_id INT NOT NULL,
    cantidad INT NOT NULL,
    precio_unitario DOUBLE NOT NULL,
    FOREIGN KEY (sale_id) REFERENCES sales(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS stock_movements (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    tipo ENUM('venta','recepcion','ajuste') NOT NULL,
    cantidad INT NOT NULL,
    usuario_id INT NOT NULL,
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    nota VARCHAR(255),
    FOREIGN KEY (product_id) REFERENCES products(id),
    FOREIGN KEY (usuario_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS purchase_orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    cantidad INT NOT NULL,
    fecha_pedido DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_estimada_llegada DATETIME,
    estado ENUM('pendiente','en_transito','recibido') DEFAULT 'pendiente',
    origen VARCHAR(40) DEFAULT 'China',
    FOREIGN KEY (product_id) REFERENCES products(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS model_runs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    algoritmo VARCHAR(80) NOT NULL,
    version VARCHAR(40) NOT NULL,
    mase DOUBLE,
    wape DOUBLE,
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    parametros_json TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS forecasts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    model_run_id INT NOT NULL,
    product_id INT,
    fecha_objetivo DATETIME NOT NULL,
    valor DOUBLE NOT NULL,
    intervalo_inf DOUBLE,
    intervalo_sup DOUBLE,
    FOREIGN KEY (model_run_id) REFERENCES model_runs(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS audit_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT,
    accion VARCHAR(80) NOT NULL,
    entidad VARCHAR(80) NOT NULL,
    entidad_id INT,
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    detalle TEXT,
    FOREIGN KEY (usuario_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
