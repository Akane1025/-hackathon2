import ddf.minim.*;
import ddf.minim.ugens.*;

Minim minim;
AudioOutput out;

// =========================
// スネア用Instrument
// =========================

class SnareInstrument implements Instrument
{
  Noise noise;
  Oscil body;

  Line noiseEnv;
  Line bodyEnv;

  SnareInstrument()
  {
    // =====================
    // スナッピー成分
    // =====================

    noise = new Noise(0.0, Noise.Tint.WHITE);

    // =====================
    // 胴鳴り
    // =====================

    body = new Oscil(180, 0.0, Waves.SINE);

    // =====================
    // エンベロープ
    // =====================

    noiseEnv = new Line();
    bodyEnv = new Line();

    // 振幅へ接続
    noiseEnv.patch(noise.amplitude);
    bodyEnv.patch(body.amplitude);
  }

  // 再生開始
  void noteOn(float duration)
  {
    // 超高速減衰
    noiseEnv.activate(duration, 0.8, 0.0);
    bodyEnv.activate(duration, 0.25, 0.0);

    // 出力へ接続
    noise.patch(out);
    body.patch(out);
  }

  // 停止
  void noteOff()
  {
    noise.unpatch(out);
    body.unpatch(out);
  }
}

void setup()
{
  size(500, 200);

  minim = new Minim(this);
  out = minim.getLineOut();

  // BPM
  out.setTempo(100);
}

void draw()
{
  background(20);

  fill(255);
  textAlign(CENTER, CENTER);
  textSize(20);

  text("Press P : Snare", width/2, height/2);
}

void keyPressed()
{
  if (key == 'p')
  {
    // 開始時刻, 長さ, Instrument
    out.playNote(0.0, 1.0, new SnareInstrument());
  }
}

//スネア、授業資料もとにしたVer？？
