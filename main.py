text.contains('انتقال الماس'))
async def transfer_diamond(m:Message,state:FSMContext): await state.update_data(kind='diamonds'); await state.set_state(Flow.transfer_id); await m.answer('شناسه عددی گیرنده را ارسال کنید.',reply_markup=back_kb())
@dp.message(Flow.transfer_id)
async def transfer_id(m:Message,state:FSMContext):
    if not m.text or not m.text.isdigit(): await m.answer('شناسه باید عددی باشد.'); return
    await state.update_data(target=int(m.text)); await state.set_state(Flow.transfer_amount); await m.answer('مقدار را ارسال کنید.',reply_markup=back_kb())
@dp.message(Flow.transfer_amount)
async def transfer_amount(m:Message,state:FSMContext):
    if not m.text or not m.text.isdigit() or int(m.text)<=0: await m.answer('مقدار نامعتبر است.'); return
    d=((F. lot:
        c.c=db(); winner=c.execute('SELECT id FROM users ORDER BY total_views DESC LIMIT 1').fetchone()
                    if winner:
                        typ=getset('monthly_gift_type','coins'); field='diamonds' if typ=='diamonds' else 'coins'; c.execute(f'UPDATE users SET {field}={field}+?,gift=gift+? WHERE id=?',(amount,amount,winner['id'])); c.commit()
                    c.close()
                setset('last_gift_month',month)
        except Exception: pass
        await asyncio.sleep(60)
@asynccontextmanager
async def lifespan(app):
    init_db()
    if WEBHOOK_URL: await bot.set_webhook(WEBHOOK_URL.rstrip('/')+'/telegram/webhook')
    task=asyncio.create_task(scheduler()); yield; task.cancel(); await bot.delete_webhook(); await bot.session.close()
app=FastAPI(lifespan=lifespan)
@app.get('/')
async def root(): return {'status':'ok','bot':'ViewCoin'}
@app.post('/telegram/webhook')
async def webhook(request:Request): data=await request.json(); await dp.feed_raw_update(bot,data); return {'ok':True}
