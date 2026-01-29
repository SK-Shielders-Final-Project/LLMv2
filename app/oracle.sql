CREATE TABLE users (
    user_id     BIGINT AUTO_INCREMENT PRIMARY KEY,
    username    VARCHAR(50) NOT NULL UNIQUE,
    name        VARCHAR(100) NOT NULL,
    password    VARCHAR(255) NOT NULL,
    email       VARCHAR(100),
    phone       VARCHAR(20),
    card_number VARCHAR(20),
    total_point BIGINT DEFAULT 0,
    pass        VARCHAR(100),
    admin_level TINYINT DEFAULT 0 COMMENT '0: 사용자, 1: 관리자, 2: 상위 관리자',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE files (
    file_id       BIGINT AUTO_INCREMENT PRIMARY KEY,
    category      VARCHAR(50),
    original_name VARCHAR(255),
    file_name     VARCHAR(255),
    ext           VARCHAR(10),
    path          VARCHAR(500),
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE notices (
    notice_id  BIGINT AUTO_INCREMENT PRIMARY KEY,
    title      VARCHAR(200) NOT NULL,
    content    TEXT,
    file_id    BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_notice_file
        FOREIGN KEY (file_id) REFERENCES files(file_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE inquiries (
    inquiry_id  BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id     BIGINT NOT NULL,
    title       VARCHAR(200) NOT NULL,
    content     TEXT,
    image_url   VARCHAR(500),
    file_id     BIGINT,
    admin_reply TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_inquiry_user
        FOREIGN KEY (user_id) REFERENCES users(user_id),
    CONSTRAINT fk_inquiry_file
        FOREIGN KEY (file_id) REFERENCES files(file_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE chat (
    chat_id    BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id    BIGINT NOT NULL,
    admin_id   BIGINT NOT NULL,
    chat_msg   VARCHAR(4000),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_chat_user
        FOREIGN KEY (user_id) REFERENCES users(user_id),
    CONSTRAINT fk_chat_admin
        FOREIGN KEY (admin_id) REFERENCES users(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE bikes (
    bike_id       BIGINT AUTO_INCREMENT PRIMARY KEY,
    serial_number VARCHAR(100) UNIQUE,
    model_name    VARCHAR(100),
    status        VARCHAR(20) COMMENT 'AVAILABLE, IN_USE, REPAIRING',
    latitude      DECIMAL(10,8),
    longitude     DECIMAL(11,8),
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE rentals (
    rental_id      BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id        BIGINT NOT NULL,
    bike_id        BIGINT NOT NULL,
    start_time     TIMESTAMP NULL,
    end_time       TIMESTAMP NULL,
    total_distance DECIMAL(10,2),
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_rental_user
        FOREIGN KEY (user_id) REFERENCES users(user_id),
    CONSTRAINT fk_rental_bike
        FOREIGN KEY (bike_id) REFERENCES bikes(bike_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE payments (
    payment_id     BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id        BIGINT NOT NULL,
    amount         BIGINT NOT NULL,
    payment_status VARCHAR(20) COMMENT 'COMPLETED, CANCELLED',
    payment_method VARCHAR(50),
    transaction_id VARCHAR(100),
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_payment_user
        FOREIGN KEY (user_id) REFERENCES users(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


