# Регламент проверки восстановления

Раз в месяц. Бэкап, который ни разу не разворачивали, бэкапом не является.

1. Взять свежий дамп из хранилища:
   ```bash
   aws s3 cp s3://$S3_BUCKET/rebook_ГГГГ-ММ-ДД_ЧЧММ.sql.gz . --endpoint-url $S3_ENDPOINT
   ```
2. Поднять чистую базу рядом с рабочей:
   ```bash
   createdb -U postgres rebook_restore_check
   gunzip -c rebook_*.sql.gz | psql -U postgres -d rebook_restore_check
   ```
3. Проверить, что данные на месте (числа сверить с рабочей базой):
   ```sql
   SELECT count(*) FROM salons;
   SELECT count(*) FROM bookings WHERE starts_at > now() - interval '30 days';
   SELECT max(sent_at) FROM message_log;
   ```
4. Убрать проверочную базу: `dropdb -U postgres rebook_restore_check`
5. Записать в журнал: дата, размер дампа, время восстановления, замечания.

Если восстановление заняло больше 15 минут или числа разошлись — разобраться
до следующего бэкапа, а не «когда-нибудь».
