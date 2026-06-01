import ddf.minim.*;
import ddf.minim.ugens.*;

Minim minim;
AudioOutput out;

class SnareInstrument implements Instrument
{
  // ノイズ
  Noise noise;

  // 胴鳴り
  Oscil body;

  // ADSR
  ADSR noiseADSR;
  ADSR bodyADSR;

  SnareInstrument()
  {
    // =====================
    // ノイズ
    // =====================

    noise = new Noise(0.5, Noise.Tint.PINK);

    // =====================
    // 胴鳴り
    // =====================

    body = new Oscil(90, 0.6, Waves.SINE);

    // =====================
    // ADSR設定
    // attack, decay, sustain, release
    // =====================

    noiseADSR = new ADSR(
      0.8,   // 最大振幅
      0.001, // attack
      0.12,  // decay
      0.0,   // sustain
      0.05   // release
    );

    bodyADSR = new ADSR(
      0.6,
      0.001,
      0.08,
      0.0,
      0.05
    );

    // 接続
    noise.patch(noiseADSR);
    body.patch(bodyADSR);

    noiseADSR.patch(out);
    bodyADSR.patch(out);
  }

  void noteOn(float duration)
  {
    noiseADSR.noteOn();
    bodyADSR.noteOn();
  }

  void noteOff()
  {
    noiseADSR.noteOff();
    bodyADSR.noteOff();
  }
}

void setup()
{
  size(500, 200);

  minim = new Minim(this);
  out = minim.getLineOut();

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
    out.playNote(0.0, 0.15, new SnareInstrument());
  }
}
