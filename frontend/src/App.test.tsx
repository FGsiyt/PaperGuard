import React from 'react';
import {afterEach,beforeEach,describe,it,expect,vi} from 'vitest';
import {render,screen,fireEvent,waitFor,cleanup,within} from '@testing-library/react';
import {App} from './main';

afterEach(()=>cleanup());
beforeEach(()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>[]})));
});

describe('PaperGuard release interactions',()=>{
  it('shows an empty workspace without invented tasks',async()=>{
    render(<App/>);
    expect(await screen.findByText('还没有核验任务')).toBeTruthy();
    expect(screen.queryByText('he2016resnet')).toBeNull();
  });

  it('submits the selected local project and offline mode',async()=>{
    const calls:Array<{path:string;body:any}>=[];
    vi.stubGlobal('fetch',vi.fn(async(path:string,init?:RequestInit)=>{
      if(init?.method==='POST'){
        calls.push({path,body:JSON.parse(String(init.body))});
        return {ok:true,json:async()=>({task_id:'fixture_task',status:'queued',progress:0,current_stage:'queued',references:[],findings:[],error_summary:[],options:{},merged_pages:0})};
      }
      if(path==='/api/tasks/fixture_task')return {ok:true,json:async()=>({task_id:'fixture_task',status:'partial',progress:100,current_stage:'partial',references:[],findings:[],error_summary:[],options:{},merged_pages:0})};
      return {ok:true,json:async()=>[]};
    }));
    render(<App/>);
    fireEvent.click(screen.getByRole('button',{name:/新建核验/}));
    fireEvent.change(screen.getByPlaceholderText('C:\\Research\\my_paper'),{target:{value:'C:\\Research\\fixture'}});
    fireEvent.click(screen.getByLabelText(/离线模式/));
    fireEvent.click(screen.getByRole('button',{name:/开始核验/}));
    await waitFor(()=>expect(calls.length).toBe(1));
    expect(calls[0].path).toBe('/api/tasks');
    expect(calls[0].body.project_path).toBe('C:\\Research\\fixture');
    expect(calls[0].body.offline).toBe(true);
    await waitFor(()=>expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('keeps import failures visible inside the open dialog',async()=>{
    vi.stubGlobal('fetch',vi.fn(async(_path:string,init?:RequestInit)=>init?.method==='POST'?{ok:false,json:async()=>({detail:'Cannot uniquely identify main .tex'})}:{ok:true,json:async()=>[]}));
    render(<App/>);
    fireEvent.click(screen.getByRole('button',{name:/新建核验/}));
    fireEvent.change(screen.getByPlaceholderText('C:\\Research\\my_paper'),{target:{value:'missing'}});
    fireEvent.click(screen.getByRole('button',{name:/开始核验/}));
    const dialog=screen.getByRole('dialog');
    expect(await within(dialog).findByRole('alert')).toBeTruthy();
    expect(within(dialog).getByRole('alert').textContent).toContain('Cannot uniquely identify');
  });
});
