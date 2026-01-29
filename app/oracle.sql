create table BIKES
(
    BIKE_ID       NUMBER(19) generated as identity
        primary key,
    CREATED_AT    TIMESTAMP(6),
    LATITUDE      FLOAT(53),
    LONGITUDE     FLOAT(53),
    MODEL_NAME    VARCHAR2(100 char),
    SERIAL_NUMBER VARCHAR2(100 char)
        constraint UK_JS67J56VCHUBESAKNDL11IDUW
            unique,
    STATUS        VARCHAR2(20 char),
    UPDATED_AT    TIMESTAMP(6)
)
/

create table FILES
(
    FILE_ID       NUMBER(19) generated as identity
        primary key,
    CATEGORY      VARCHAR2(255 char),
    CREATED_AT    TIMESTAMP(6),
    EXT           VARCHAR2(255 char),
    FILE_NAME     VARCHAR2(255 char),
    ORIGINAL_NAME VARCHAR2(255 char),
    PATH          VARCHAR2(255 char)
)
/

create table INQUIRIES
(
    INQUIRY_ID  NUMBER(19) generated as identity
        primary key,
    ADMIN_REPLY CLOB,
    CONTENT     CLOB,
    CREATED_AT  TIMESTAMP(6),
    IMAGE_URL   VARCHAR2(500 char),
    TITLE       VARCHAR2(200 char) not null,
    UPDATED_AT  TIMESTAMP(6),
    FILE_ID     NUMBER(19)
        constraint UK_56Y5K898INY21K8FRYW3AX3J1
            unique
        constraint FK7COJ5R8NPGS5E5MVH090S88UB
            references FILES,
    USER_ID     NUMBER(19)         not null
        constraint FKFKS94Q8SOBCUIBRUDBR3IM380
            references USERS
)
/

create table PAYMENTS
(
    PAYMENT_ID     NUMBER(19) generated as identity
        primary key,
    AMOUNT         NUMBER(19) not null,
    CREATED_AT     TIMESTAMP(6),
    ORDER_ID       VARCHAR2(100 char),
    PAYMENT_KEY    VARCHAR2(100 char),
    PAYMENT_METHOD VARCHAR2(50 char),
    PAYMENT_STATUS VARCHAR2(20 char)
        check (payment_status in ('READY', 'DONE', 'CANCELED', 'PARTIAL_CANCELED')),
    REMAIN_AMOUNT  NUMBER(19) not null,
    USER_ID        NUMBER(19) not null
        constraint FKJ94HGY9V5FW1MUNB90TAR2EJE
            references USERS
)
/

create table RENTALS
(
    RENTAL_ID      NUMBER(19) generated as identity
        primary key,
    CREATED_AT     TIMESTAMP(6),
    END_TIME       TIMESTAMP(6),
    START_TIME     TIMESTAMP(6),
    TOTAL_DISTANCE FLOAT(53),
    BIKE_ID        NUMBER(19) not null
        constraint FKP4Y1C0F9H725HS66Q96OY64R
            references BIKES,
    USER_ID        NUMBER(19) not null
        constraint FKTNHD1OBJF2MLB6AG6K726U269
            references USERS
)
/

create table USED_COUPON
(
    USED_COUPON_ID NUMBER(19) generated as identity
        primary key,
    COUPON_CODE    VARCHAR2(255 char) not null
        constraint UK_BW0HN0WNSI9HOAXI5YNXXL0UR
            unique,
    CREATED_AT     TIMESTAMP(6),
    USER_ID        NUMBER(19)         not null
)
/

create table USERS
(
    USER_ID     NUMBER(19) generated as identity
        primary key,
    ADMIN_LEVEL NUMBER(10),
    CREATED_AT  TIMESTAMP(6),
    EMAIL       VARCHAR2(100 char),
    NAME        VARCHAR2(100 char) not null,
    PASSWORD    VARCHAR2(255 char) not null,
    PHONE       VARCHAR2(20 char),
    TOTAL_POINT NUMBER(19),
    UPDATED_AT  TIMESTAMP(6),
    USERNAME    VARCHAR2(50 char)  not null
        constraint UK_R43AF9AP4EDM43MMTQ01ODDJ6
            unique
)
/

