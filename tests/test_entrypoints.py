def test_volcsarvatory_monitoring(script_runner):
    ret = script_runner.run(['python', '-m', 'volcsarvatory_monitoring', '-h'])
    assert ret.success
