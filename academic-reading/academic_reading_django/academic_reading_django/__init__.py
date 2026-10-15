"""Django project package."""

try:
    import pymysql

    pymysql.install_as_MySQLdb()
except ImportError:  # pragma: no cover - PyMySQL is expected in production images
    pass
