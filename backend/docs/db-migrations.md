# Database setup & migrations

1. **Create Postgres database**
   ```bash
   createdb aim
   ```

2. **Configure `.env`**
   ```env
   DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/aim
   ```

3. **Run migrations**
   ```bash
   cd backend
   alembic upgrade head
   ```

4. **Generate new migrations**
   ```bash
   alembic revision -m "add new table"
   alembic upgrade head
   ```
