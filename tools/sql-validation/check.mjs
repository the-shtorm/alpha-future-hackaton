import { PGlite } from '@electric-sql/pglite';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
process.chdir(path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..'));
process.on('uncaughtException', error => {
  console.error(JSON.stringify({message:error.message,code:error.code,detail:error.detail,where:error.where},null,2));
  process.exit(1);
});

const db = new PGlite();
await db.waitReady;
console.log((await db.query('select version()')).rows[0].version);
await db.exec('CREATE ROLE credit_app NOLOGIN; CREATE ROLE credit_migrator NOLOGIN; CREATE SCHEMA credit AUTHORIZATION credit_migrator; REVOKE CREATE ON SCHEMA public FROM PUBLIC; SET ROLE credit_migrator;');
const migrations = 'backend/src/main/resources/db/migration';
for (const file of (await fs.readdir(migrations)).filter(f => f.endsWith('.sql')).sort()) {
  await db.exec('BEGIN;\n' + await fs.readFile(path.join(migrations, file), 'utf8') + '\nCOMMIT;');
  console.log('Migration OK: ' + file);
}
await db.exec(await fs.readFile('backend/src/main/resources/db/demo/R__synthetic_product_catalog.sql', 'utf8'));
await db.exec(await fs.readFile('backend/src/main/resources/db/demo/R__synthetic_product_catalog.sql', 'utf8'));
const catalogCount = Number((await db.query('SELECT count(*) FROM credit.credit_product')).rows[0].count);
const documentTypeCount = Number((await db.query('SELECT count(*) FROM credit.document_type')).rows[0].count);
if (catalogCount !== 15 || documentTypeCount !== 35) throw new Error('Unexpected catalog size');
console.log('Catalog: 15 products, 35 document types; repeatable seed is idempotent');
await db.exec(await fs.readFile('backend/src/test/resources/db/database_invariants.sql', 'utf8'));
console.log('Integrity and lifecycle fixtures passed');
if (Number((await db.query('SELECT count(*) FROM credit.loan_application')).rows[0].count) !== 0) {
  throw new Error('Test fixtures were not rolled back');
}
const roles = await db.query(`SELECT
  has_table_privilege('credit_app','credit.loan_application','INSERT') AS can_insert_application,
  has_table_privilege('credit_app','credit.application_status_history','INSERT') AS can_forge_history,
  has_table_privilege('credit_app','credit.credit_product_version','UPDATE') AS can_rewrite_catalog,
  has_schema_privilege('credit_app','credit','CREATE') AS can_change_schema`);
console.log('Runtime privileges:', roles.rows);
if (!roles.rows[0].can_insert_application || roles.rows[0].can_forge_history || roles.rows[0].can_rewrite_catalog || roles.rows[0].can_change_schema) {
  throw new Error('Unexpected runtime privileges');
}
await db.exec(`BEGIN;
  SET LOCAL ROLE credit_app;
  INSERT INTO credit.app_user(id,login,password_hash,display_name)
    VALUES ('10000000-0000-0000-0000-000000000001','runtime-test','{bcrypt}fixture','Runtime role');
  INSERT INTO credit.party(id,party_kind,name) VALUES ('10000000-0000-0000-0000-000000000002','LLC','Runtime company');
  INSERT INTO credit.loan_application(applicant_party_id,created_by,product_version_id,requested_amount,requested_term_months,purpose,form_version)
    SELECT '10000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000001',id,1000000,12,'WORKING_CAPITAL','test'
      FROM credit.credit_product_version LIMIT 1;
  ROLLBACK;`);
console.log('Runtime INSERT and automatic protected history passed');
console.log('Tables:', (await db.query("select count(*) from information_schema.tables where table_schema='credit' and table_type='BASE TABLE'")).rows);
await db.close();
