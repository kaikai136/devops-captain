import mysql from '../assets/database-logos/mysql.png';
import mariadb from '../assets/database-logos/mariadb.png';
import postgresql from '../assets/database-logos/postgresql.png';
import mongodb from '../assets/database-logos/mongodb.png';
import redis from '../assets/database-logos/redis.svg';
import kingbase from '../assets/database-logos/kingbase.png';
import sqlserver from '../assets/database-logos/sqlserver.png';
import clickhouse from '../assets/database-logos/clickhouse.png';
import sqlite from '../assets/database-logos/sqlite.png';
import oracle from '../assets/database-logos/oracle.png';
import dameng from '../assets/database-logos/dameng.png';
import doris from '../assets/database-logos/doris.svg';
import starrocks from '../assets/database-logos/starrocks.svg';
import duckdb from '../assets/database-logos/duckdb.png';
import tdengine from '../assets/database-logos/tdengine.png';

const databaseBrandLogos: Readonly<Record<string, string>> = {
  mysql, mariadb, postgresql, mongodb, redis, kingbase, sqlserver,
  clickhouse, sqlite, oracle, dameng, doris, starrocks, duckdb, tdengine,
};

export function databaseBrandLogo(dbType: string): string | undefined {
  const key = dbType.trim().toLowerCase();
  return Object.hasOwn(databaseBrandLogos, key) ? databaseBrandLogos[key] : undefined;
}
