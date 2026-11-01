-- Seed data. Run after migrations. sources come from sources.csv (scripts/seed.py loads it).
-- NOTE: service fee amounts below are PLACEHOLDERS until the business sets real prices.

insert into public.allowed_domains (domain, authority) values
  ('gov.uk','UK Government'), ('vfsglobal.com','VFS Global'), ('tlscontact.com','TLScontact'),
  ('evisa.gov.tr','Türkiye e-Visa'), ('mfa.gov.tr','Türkiye MFA'), ('diplo.de','German Foreign Office'),
  ('u.ae','UAE Government'), ('icp.gov.ae','UAE ICP'), ('gdrfad.gov.ae','GDRFA Dubai'),
  ('imi.gov.my','Malaysia Immigration'), ('visitsaudi.com','Saudi Tourism Authority'),
  ('nusuk.sa','Nusuk'), ('mofa.gov.sa','Saudi MOFA'), ('mora.gov.pk','MoRA Pakistan'),
  ('beoe.gov.pk','BEOE'), ('fia.gov.pk','FIA'), ('dgip.gov.pk','DGIP'), ('nadra.gov.pk','NADRA')
on conflict do nothing;

insert into public.service_fees (service_type, destination_country, amount_minor, currency, per, description_en, description_ur) values
  ('visit_visa', null, 1500000, 'PKR', 'traveller', 'Rahbar service fee: assessment, document review, application pack, submission handling', 'رہبر سروس فیس: جائزہ، دستاویزات کی جانچ، درخواست کی تیاری، جمع کروانا'),
  ('umrah_package', null, 1000000, 'PKR', 'traveller', 'Rahbar service fee: Umrah package planning and coordination', 'رہبر سروس فیس: عمرہ پیکج کی منصوبہ بندی اور رابطہ کاری'),
  ('flight', null, 250000, 'PKR', 'booking', 'Rahbar service fee: flight booking', 'رہبر سروس فیس: فلائٹ بکنگ'),
  ('hotel', null, 150000, 'PKR', 'booking', 'Rahbar service fee: hotel booking', 'رہبر سروس فیس: ہوٹل بکنگ'),
  ('tour', null, 500000, 'PKR', 'case', 'Rahbar service fee: tour plan', 'رہبر سروس فیس: ٹور پلان'),
  ('scam_check', null, 0, 'PKR', 'case', 'Scam Checker is free', 'اسکیم چیکر مفت ہے')
on conflict do nothing;

insert into public.refund_policies (service_type, rules, text_en, text_ur) values
  ('visit_visa',
   '[{"before_status":"documents_review","refund_percent":100},{"before_status":"submitted","refund_percent":50},{"before_status":null,"refund_percent":0}]',
   'Full refund of our service fee before document review starts; 50% before submission; no refund of our fee after submission. Government and VFS fees follow their own rules and are usually non-refundable. A refusal does not make our fee refundable, because we never promise approval.',
   'دستاویزات کی جانچ شروع ہونے سے پہلے ہماری سروس فیس مکمل واپس؛ جمع کروانے سے پہلے 50٪؛ جمع کروانے کے بعد واپسی نہیں۔ سرکاری اور (VFS) فیس اپنے قوانین کے مطابق ہوتی ہیں اور عموماً ناقابلِ واپسی ہیں۔ ویزا مسترد ہونے پر بھی ہماری فیس واپس نہیں ہوتی کیونکہ ہم کبھی منظوری کا وعدہ نہیں کرتے۔'),
  ('umrah_package',
   '[{"before_status":"booked","refund_percent":100},{"before_status":null,"refund_percent":0}]',
   'Full refund of our service fee before anything is booked. After booking, airline, hotel and partner cancellation rules apply and are shown on each line before you pay.',
   'بکنگ سے پہلے ہماری سروس فیس مکمل واپس۔ بکنگ کے بعد ایئرلائن، ہوٹل اور پارٹنر کے منسوخی کے قوانین لاگو ہوں گے جو ادائیگی سے پہلے ہر لائن پر دکھائے جاتے ہیں۔'),
  ('flight', '[{"before_status":"booked","refund_percent":100},{"before_status":null,"refund_percent":0}]',
   'Our fee is refunded in full if the ticket is not issued. After issue, the airline fare rules apply.',
   'اگر ٹکٹ جاری نہ ہو تو ہماری فیس مکمل واپس۔ ٹکٹ جاری ہونے کے بعد ایئرلائن کے کرایہ قوانین لاگو ہوں گے۔'),
  ('hotel', '[{"before_status":"booked","refund_percent":100},{"before_status":null,"refund_percent":0}]',
   'Our fee is refunded in full if the booking is not made. After booking, the hotel cancellation policy shown at checkout applies.',
   'اگر بکنگ نہ ہو تو ہماری فیس مکمل واپس۔ بکنگ کے بعد ہوٹل کی وہ منسوخی پالیسی لاگو ہوگی جو ادائیگی کے وقت دکھائی گئی۔'),
  ('tour', '[{"before_status":"booked","refund_percent":100},{"before_status":null,"refund_percent":0}]',
   'Full refund of the tour planning fee before any booking.', 'کسی بکنگ سے پہلے ٹور پلاننگ فیس مکمل واپس۔'),
  ('scam_check', '[]', 'Free service.', 'مفت سروس۔')
on conflict do nothing;

insert into public.scheduled_jobs (name, type, payload, every) values
  ('daily_crawl', 'crawl_due_sources', '{}', '1 hour'),
  ('quote_expiry', 'expire_quotes', '{}', '15 minutes'),
  ('document_retention', 'retention_sweep', '{"days":90}', '1 day'),
  ('booking_polling', 'poll_booking_status', '{}', '30 minutes')
on conflict do nothing;

insert into public.partners (id, name, kind, licence_number, licence_authority, licence_expiry, contract_terms, active) values
  ('00000000-0000-0000-0000-0000000000a1', 'Sandbox Umrah Operator (demo)', 'umrah_operator', 'DEMO-UMRAH-001', 'Ministry of Religious Affairs (demo)', '2027-12-31', '{"note":"demo partner for development only"}', true)
on conflict do nothing;
