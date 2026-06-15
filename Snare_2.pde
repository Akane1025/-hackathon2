import ddf.minim.*;
import ddf.minim.ugens.*;
import ddf.minim.effects.*;

Minim minim;
AudioOutput out;
AudioRecorder recorder;
boolean recorded = false;


class SnareInstrument implements Instrument
{
  // ノイズ
  Noise noise;

  // 胴鳴り
  Oscil body;
  
  //ローパスフィルタ
  LowPassSP lp;

  // ADSR
  ADSR noiseADSR;
  ADSR bodyADSR;

  SnareInstrument()
  {
    noise = new Noise(0.35, Noise.Tint.PINK);
    lp = new LowPassSP( 4500, out.sampleRate());
    body = new Oscil(180, 0.3, Waves.SINE);

    noiseADSR = new ADSR(1.0, 0.001, 0.25, 0.0, 0.4);
    bodyADSR  = new ADSR(0.6, 0.001, 0.25, 0.0, 0.2);
    

    // 接続
    noise.patch(lp);
    lp.patch(noiseADSR);
    noiseADSR.patch(out);
    body.patch(bodyADSR);
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

//6_15最新版
